"""export_clip.py — a kit clip OUT of Roblox (2026-10-24): an R6 clip as a glTF 2.0 binary (.glb) any engine or DCC
loads (Blender, Unity, Unreal, three.js, Godot), and an .fbx through Blender. An R6 body is six rigid boxes, so the
animation is NODE animation (no skinning): each part's world transform per frame, the root travel composed in, and a
sword clip's blade as its own animated node. Roblox and glTF are both right-handed, +Y up, in studs (1 stud = 1 unit).

    python kit/anim/export_clip.py <clip.json> <out.glb> [--fbx <out.fbx>] [--gltf]
    python kit/anim/export_clip.py <cutscene scene.json> <out.glb> --cutscene [--fbx <out.fbx>] [--gltf]
    (--gltf: the same scene as <out>.gltf too - one JSON text file, the buffer embedded)
"""
import json
import math
import os
import struct
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import clip as C  # noqa: E402
import motion_lib as ML  # noqa: E402

PARTS = ["Torso", "Head", "Right Arm", "Left Arm", "Right Leg", "Left Leg"]
COLOURS = {"Torso": (0.05, 0.41, 0.67), "Head": (0.96, 0.8, 0.19), "Right Arm": (0.96, 0.8, 0.19),
           "Left Arm": (0.96, 0.8, 0.19), "Right Leg": (0.64, 0.75, 0.28), "Left Leg": (0.64, 0.75, 0.28),
           "Sword": (0.82, 0.84, 0.88)}


def box(size):
    """a box centred on 0: 24 vertices (flat normals), 36 indices"""
    hx, hy, hz = (s / 2 for s in size)
    pos, nrm, idx = [], [], []
    for axis in range(3):
        for sign in (1.0, -1.0):
            n = [0.0, 0.0, 0.0]
            n[axis] = sign
            u, v = [(a for a in range(3) if a != axis)][0]
            base = len(pos)
            for du, dv in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                p = [0.0, 0.0, 0.0]
                p[axis] = sign * (hx, hy, hz)[axis]
                p[u] = du * (hx, hy, hz)[u]
                p[v] = dv * (hx, hy, hz)[v]
                pos.append(p)
                nrm.append(n)
            a, b, c, d = base, base + 1, base + 2, base + 3
            pa, pb, pc = (np.asarray(pos[k]) for k in (a, b, c))
            outward = float(np.cross(pb - pa, pc - pa) @ np.asarray(n)) > 0     # (counter-clockwise seen from outside)
            idx += [a, b, c, a, c, d] if outward else [a, c, b, a, d, c]
    return pos, nrm, idx


def continuous(qs):
    """quaternions with no sign flips between neighbours (q and -q are one rotation; a LINEAR player would spin)"""
    out = []
    for q in qs:
        if out and float(np.dot(out[-1], q)) < 0:
            q = [-v for v in q]
        out.append(list(q))
    return out


def tracks(clip, rig):
    """{node: (times, [translation], [rotation xyzw])} in the clip's world (studs), the root travel composed in"""
    W = C.world_frames(clip, rig)
    times = [float(t) for t in clip["times"]]
    out = {}
    for part in PARTS:
        if part not in W[0]:
            continue
        out[part] = (times, [[float(v) for v in w[part][:3, 3]] for w in W],
                     continuous([C.mat_quat(w[part][:3, :3]) for w in W]))
    sw = clip.get("sword") or {}
    tips, grips = sw.get("tip") or [], sw.get("grip_path") or []
    if len(tips) == len(times) and len(grips) == len(times):
        root = clip.get("root") if isinstance(clip.get("root"), list) and len(clip["root"]) == len(times) else None
        edges = sw.get("edge") if isinstance(sw.get("edge"), list) and len(sw["edge"]) == len(times) else None
        tr, rot = [], []
        for i in range(len(times)):
            g, t = np.asarray(grips[i], float), np.asarray(tips[i], float)
            y = t - g
            y = y / (np.linalg.norm(y) or 1.0)
            e = np.asarray(edges[i], float) if edges else np.array([0.0, 0.0, -1.0])
            z = e - y * float(e @ y)
            if np.linalg.norm(z) < 1e-6:                       # (no edge: any axis the blade is not along)
                z = np.cross(y, [1.0, 0.0, 0.0] if abs(y[0]) < 0.9 else [0.0, 0.0, 1.0])
            z = z / np.linalg.norm(z)
            x = np.cross(y, z)
            M = np.eye(4)
            M[:3, :3] = np.column_stack([x, y, z])
            # the box spans the WHOLE sword - from the pommel (half the hand spacing behind the grip point, as
            # strike.py lays it: tip = grip + d (length - spacing / 2)) to the tip - not the grip-to-tip span
            L, sp = sw.get("length"), sw.get("grip")
            M[:3, 3] = g + y * (float(L) / 2 - float(sp) / 2) if isinstance(L, (int, float)) and isinstance(
                sp, (int, float)) else (g + t) / 2
            if root:
                R = np.eye(4)
                R[:3, :3] = C.quat_mat(root[i][:4])
                R[:3, 3] = root[i][4:7]
                M = R @ M
            tr.append([float(v) for v in M[:3, 3]])
            rot.append(C.mat_quat(M[:3, :3]))
        out["Sword"] = (times, tr, continuous(rot))
    return out


LOOKS = {"noob": COLOURS,
         "shadow": {"Torso": (0.16, 0.1, 0.24), "Head": (0.08, 0.08, 0.1), "Right Arm": (0.08, 0.08, 0.1),
                    "Left Arm": (0.08, 0.08, 0.1), "Right Leg": (0.12, 0.12, 0.14), "Left Leg": (0.12, 0.12, 0.14),
                    "Sword": (0.82, 0.84, 0.88)}}


def glb(clip, rig, path):
    """write the clip as one .glb -> {nodes, frames, duration}"""
    return glb_actors({None: (clip, "noob")}, rig, path, str(clip.get("name") or os.path.splitext(os.path.basename(path))[0]))


def look_quat(loc, target, prev=None):
    """the rotation of a glTF camera node at `loc` looking at `target` (a glTF camera looks down its own -Z, +Y up);
    a key whose target IS its position has no direction: it keeps `prev` (or looks down -Z)"""
    f = np.asarray(target, float) - np.asarray(loc, float)
    if np.linalg.norm(f) < 1e-9:
        return list(prev) if prev is not None else [0.0, 0.0, 0.0, 1.0]
    f = f / np.linalg.norm(f)
    z = -f
    up = np.array([0.0, 1.0, 0.0]) if abs(f[1]) < 0.999 else np.array([0.0, 0.0, 1.0])
    x = np.cross(up, z)
    x = x / (np.linalg.norm(x) or 1.0)
    y = np.cross(z, x)
    return C.mat_quat(np.column_stack([x, y, z]))


def glb_actors(actors, rig, path, name, camera=None, fps=60, yfov=None):
    """several actors' clips (actor -> (clip, look[, visible per frame]); actor None = one clip, its parts unprefixed)
    and, for a cutscene, its planned CAMERA (per frame {loc, target} at `fps`: an animated glTF camera, the shot as
    directed) in ONE .glb, one
    animation over them all (a cutscene: two swordsmen on one clock) -> {nodes, frames, duration}"""
    blob = bytearray()
    views, accessors = [], []

    def add(data, fmt, comps, target=None, minmax=False):
        while len(blob) % 4:
            blob.append(0)
        off = len(blob)
        flat = [v for row in data for v in (row if isinstance(row, (list, tuple)) else [row])]
        blob.extend(struct.pack(f"<{len(flat)}{fmt}", *flat))
        view = {"buffer": 0, "byteOffset": off, "byteLength": len(blob) - off}
        if target:
            view["target"] = target
        views.append(view)
        acc = {"bufferView": len(views) - 1, "componentType": 5126 if fmt == "f" else 5123,
               "count": len(data), "type": {1: "SCALAR", 3: "VEC3", 4: "VEC4"}[comps]}
        if minmax:
            arr = np.asarray(data, float).reshape(len(data), comps)
            acc["min"] = [float(v) for v in arr.min(0)]
            acc["max"] = [float(v) for v in arr.max(0)]
        accessors.append(acc)
        return len(accessors) - 1

    nodes, meshes, materials = [], [], []
    channels, samplers = [], []
    groups, all_names, frames, duration = [], [], 0, 0.0
    for actor, spec in actors.items():
        clip, look = spec[0], spec[1]
        visible = spec[2] if len(spec) > 2 else None
        tr = tracks(clip, rig)
        sizes = dict(rig["sizes"])
        sw = clip.get("sword") or {}
        sizes["Sword"] = [0.08, float(sw.get("length") or 3.6), 0.25]
        colours = LOOKS.get(look, COLOURS)
        kids = []
        for part in [n for n in PARTS + ["Sword"] if n in tr]:
            label = part if actor is None else f"{actor} {part}"
            pos, nrm, idx = box(sizes.get(part, [1, 1, 1]))
            a_pos = add(pos, "f", 3, 34962, minmax=True)
            a_nrm = add(nrm, "f", 3, 34962)
            a_idx = add(idx, "H", 1, 34963)
            materials.append({"name": label, "pbrMetallicRoughness": {
                "baseColorFactor": list(colours.get(part, (0.8, 0.8, 0.8))) + [1.0],
                "metallicFactor": 0.6 if part == "Sword" else 0.0, "roughnessFactor": 0.5}})
            meshes.append({"name": label, "primitives": [{"attributes": {"POSITION": a_pos, "NORMAL": a_nrm},
                                                          "indices": a_idx, "material": len(materials) - 1}]})
            times, tl, rl = tr[part]
            nodes.append({"name": label, "mesh": len(meshes) - 1, "translation": tl[0], "rotation": rl[0]})
            kids.append(len(nodes) - 1)
            all_names.append(label)
            a_t = add(times, "f", 1, minmax=True)
            for path_, values in (("translation", tl), ("rotation", rl)):
                samplers.append({"input": a_t, "output": add(values, "f", len(values[0])), "interpolation": "LINEAR"})
                channels.append({"sampler": len(samplers) - 1, "target": {"node": len(nodes) - 1, "path": path_}})
        frames = max(frames, len(clip["times"]))
        duration = max(duration, float(clip["times"][-1]))
        if actor is None:
            groups += kids
        else:
            nodes.append({"name": str(actor), "children": kids})
            groups.append(len(nodes) - 1)
            if visible and not all(visible):
                # hidden (a teleport's gap) = the actor's group scaled to 0, STEP: on and off on the frame
                ts = [float(t) for t in clip["times"]]
                vis = (list(visible) + [visible[-1]] * len(ts))[:len(ts)]   # (a short list keeps its last state)
                sc = [[1.0, 1.0, 1.0] if v else [0.0, 0.0, 0.0] for v in vis]
                samplers.append({"input": add(ts, "f", 1, minmax=True), "output": add(sc, "f", 3),
                                 "interpolation": "STEP"})
                channels.append({"sampler": len(samplers) - 1, "target": {"node": len(nodes) - 1, "path": "scale"}})
    cameras = []
    if camera:
        # the directed shot: 32 mm on a 36 mm sensor at 16:9 (the render's lens) unless given
        cameras.append({"type": "perspective", "name": "Planned camera", "perspective": {
            "yfov": float(yfov or 2 * math.atan(18 / 32 * 9 / 16)), "aspectRatio": 16 / 9,
            "znear": 0.1, "zfar": 1000.0}})
        ts = [i / fps for i in range(len(camera))]
        tl = [[float(v) for v in k["loc"]] for k in camera]
        rl, prev = [], None
        for k in camera:
            prev = look_quat(k["loc"], k["target"], prev)
            rl.append(prev)
        rl = continuous(rl)
        nodes.append({"name": "Planned camera", "camera": 0, "translation": tl[0], "rotation": rl[0]})
        groups.append(len(nodes) - 1)
        a_t = add(ts, "f", 1, minmax=True)
        for path_, values in (("translation", tl), ("rotation", rl)):
            samplers.append({"input": a_t, "output": add(values, "f", len(values[0])), "interpolation": "LINEAR"})
            channels.append({"sampler": len(samplers) - 1, "target": {"node": len(nodes) - 1, "path": path_}})
    nodes.append({"name": name, "children": groups})
    doc = {"asset": {"version": "2.0", "generator": "roblox-kit export_clip.py"},
           "scene": 0, "scenes": [{"name": name, "nodes": [len(nodes) - 1]}],
           "nodes": nodes, "meshes": meshes, "materials": materials,
           "animations": [{"name": name, "channels": channels, "samplers": samplers}],
           "accessors": accessors, "bufferViews": views, "buffers": [{"byteLength": len(blob)}]}
    if cameras:
        doc["cameras"] = cameras
    while len(blob) % 4:
        blob.append(0)
    doc["buffers"][0]["byteLength"] = len(blob)
    js = json.dumps(doc, separators=(",", ":")).encode("utf-8")
    js += b" " * ((4 - len(js) % 4) % 4)
    with open(path, "wb") as fh:
        fh.write(struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(blob)))
        fh.write(struct.pack("<II", len(js), 0x4E4F534A) + js)
        fh.write(struct.pack("<II", len(blob), 0x004E4942) + bytes(blob))
    return {"nodes": all_names, "frames": frames, "duration": duration}


def read_glb(path):
    """(json, bin) of a .glb - the format's own two chunks"""
    data = open(path, "rb").read()
    magic, version, total = struct.unpack_from("<III", data, 0)
    if magic != 0x46546C67 or version != 2 or total != len(data):
        raise ValueError(f"{path}: not a glTF 2.0 binary")
    n, kind = struct.unpack_from("<II", data, 12)
    if kind != 0x4E4F534A:
        raise ValueError(f"{path}: the first chunk is not JSON")
    doc = json.loads(data[20:20 + n])
    m, kind2 = struct.unpack_from("<II", data, 20 + n)
    if kind2 != 0x004E4942:
        raise ValueError(f"{path}: the second chunk is not BIN")
    return doc, data[28 + n:28 + n + m]


def gltf_json(glb_path, out_path):
    """the same scene as a .gltf (JSON, its buffer embedded as base64): one text file, for places that take JSON"""
    import base64
    doc, blob = read_glb(glb_path)
    doc["buffers"][0]["uri"] = "data:application/octet-stream;base64," + base64.b64encode(blob).decode("ascii")
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, separators=(",", ":"))
    return out_path


FBX_SCRIPT = """
import bpy, sys
src, dst = sys.argv[sys.argv.index("--") + 1:][:2]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
bpy.ops.export_scene.fbx(filepath=dst, bake_anim=True, bake_anim_use_all_actions=False, add_leaf_bones=False,
                         axis_forward="-Z", axis_up="Y")
print("FBX_OK")
"""


def fbx(glb_path, fbx_path):
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:                 # (its own folder: two exports never share a script)
        script = os.path.join(tmp, "export_fbx.py")
        with open(script, "w", encoding="utf-8") as fh:
            fh.write(FBX_SCRIPT)
        try:
            p = subprocess.run([ML.BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P", script, "--",
                                os.path.abspath(glb_path), os.path.abspath(fbx_path)],
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
        except OSError as e:
            return False, f"Blender could not run ({ML.BLENDER}): {e}"
    return p.returncode == 0 and "FBX_OK" in p.stdout and os.path.isfile(fbx_path), (p.stderr or p.stdout)[-800:]


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    src, out = argv[0], argv[1]
    if "--cutscene" in argv:
        # a planned cutscene (kit/anim/cutscene.py's scene.json): every actor's composed clip on one clock
        scene = json.load(open(src, encoding="utf-8"))
        acts = {nm: (C.load_clip(a["clip"]), a.get("look", "noob"), a.get("visible"))
                for nm, a in scene["actors"].items()}
        wrong = [nm for nm, v in acts.items() if v[0].get("rig") != "R6"]
        if wrong:
            ML.emit("fail", f"{src}: actor(s) {', '.join(wrong)} are not R6 clips", "re-plan the cutscene")
            return 1
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        info = glb_actors(acts, C.load_rig("r6"), out, scene.get("name", "Cutscene"), camera=scene.get("camera"),
                          fps=int(scene.get("fps") or 60))
        msg = f"{info['frames']} frames ({info['duration']:.2f} s), {len(acts)} actors, {len(info['nodes'])} nodes -> {out}"
        if "--gltf" in argv:
            msg += f" + {gltf_json(out, os.path.splitext(out)[0] + '.gltf')}"
        if "--fbx" in argv:
            fp = argv[argv.index("--fbx") + 1]
            ok, tail = fbx(out, fp)
            if not ok:
                ML.emit("fail", f"glb written ({msg}) but the FBX export failed: {tail}", "read Blender's output")
                return 1
            msg += f" + {fp}"
        ML.emit("pass", f"exported cutscene {scene.get('name')}: {msg}", "open it in Blender / any glTF viewer")
        return 0
    clip = C.load_clip(src)
    if clip.get("rig") != "R6":
        ML.emit("fail", f"{src} is a {clip.get('rig')} clip: export the R6 one (build/animations/<Name>.r6.clip.json)",
                "pass the .r6.clip.json")
        return 1
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    info = glb(clip, C.load_rig("r6"), out)
    msg = f"{info['frames']} frames ({info['duration']:.2f} s), nodes {', '.join(info['nodes'])} -> {out}"
    if "--gltf" in argv:
        msg += f" + {gltf_json(out, os.path.splitext(out)[0] + '.gltf')}"
    if "--fbx" in argv:
        fp = argv[argv.index("--fbx") + 1]
        ok, tail = fbx(out, fp)
        if not ok:
            ML.emit("fail", f"glb written ({msg}) but the FBX export failed: {tail}", "read Blender's output")
            return 1
        msg += f" + {fp}"
    ML.emit("pass", f"exported {clip.get('name')}: {msg}", "open it in Blender / any glTF viewer")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
