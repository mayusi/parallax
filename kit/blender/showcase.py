"""showcase.py — `kit showcase <name>`: the model PRESENTED (the third end goal beside the master and its game version).

Opens the last FULL build (build/models/<name>.blend: the joined, baked groups) under the kit's studio light and
renders into build/showcase/<name>/:
  turntable_###.png   the whole model turning once under fixed lights, from a 3/4 camera — how it reads all round
  mechanism_###.png   every joint through its travel in the order the joints need (after=: the housing opens, THEN
                      the shell lifts out, then both go back), rest held between them — that it WORKS, in motion
  showcase.json       the frames and which joint moves when (kit/blender/showcase_pack.py packs GIFs + a poster)
    blender -b --factory-startup build/models/<name>.blend -P kit/blender/showcase.py -- <name> [--frames=36]
"""

import json
import math
import os
import sys
import time
import types

import bpy
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rbx  # noqa: E402  (the studio light, the GPU switch)
import rbx_mech  # noqa: E402  (joint poses, as the build checks them)

RAMP, HOLD = 8, 3  # frames to open / close a joint, frames to hold a pose


def _args():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = {"name": a[0] if a else None, "frames": 36, "samples": 48, "size": (960, 540)}
    for x in a[1:]:
        if x.startswith("--frames="):
            out["frames"] = max(4, int(x.split("=", 1)[1]))
        elif x.startswith("--samples="):
            out["samples"] = max(4, int(x.split("=", 1)[1]))
    return out


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def _ease(t):
    return t * t * (3 - 2 * t)


def timeline(joints):
    """[{joint: value}] one absolute state per frame: each joint opens and closes in turn; a joint that waits for
    another (after={"TopHousing": "max"}) plays while that one is held open, then they close in reverse"""
    state = {n: j["min"] for n, j in joints.items()}
    frames, marks = [], []

    def ramp(n, a, b):
        for k in range(1, RAMP + 1):
            state[n] = a + (b - a) * _ease(k / RAMP)
            frames.append(dict(state))

    def hold(k=HOLD):
        frames.extend(dict(state) for _ in range(k))

    hold(2)
    waits = {n: set((j.get("after") or {}).keys()) for n, j in joints.items()}
    for n, j in joints.items():
        if waits[n]:
            continue  # played inside the joint it waits for
        start = len(frames)
        ramp(n, j["min"], j["max"])
        hold()
        for d, dj in joints.items():
            if n in waits[d]:
                ramp(d, dj["min"], dj["max"])
                hold()
                ramp(d, dj["max"], dj["min"])
        ramp(n, j["max"], j["min"])
        hold(2)
        marks.append({"joint": n, "then": [d for d in joints if n in waits[d]], "frames": [start, len(frames) - 1]})
    return frames, marks


def shot(sc, path):
    """render the scene and SAVE it (write_still alone left no file behind in a background run)"""
    bpy.ops.render.render()
    bpy.data.images["Render Result"].save_render(filepath=path, scene=sc)
    if not os.path.isfile(path):
        raise RuntimeError(f"showcase: the render was not saved to {path}")
    return os.path.basename(path)


def main():
    a = _args()
    name = a["name"]
    if not name:
        return emit("fail", "showcase: no asset name", "lune run kit showcase <name>")
    build = os.environ.get("KIT_BUILD", os.path.join(os.getcwd(), "build"))
    with open(os.path.join(build, "models", f"{name}.manifest.json"), encoding="utf-8") as fh:
        man = json.load(fh)
    out = os.path.abspath(os.path.join(build, "showcase", name))  # (a relative render path lands elsewhere)
    os.makedirs(out, exist_ok=True)
    for f in os.listdir(out):
        if f.endswith(".png") and (f.startswith("turntable_") or f.startswith("mechanism_")):
            os.remove(os.path.join(out, f))
    sc = bpy.context.scene
    objs = {}
    for g in man["groups"]:
        o = bpy.data.objects.get(name if g == "main" else f"{name}_{g}")
        if o is not None:
            objs[g] = o
    if not objs:
        return emit("fail", f"showcase: {name}.blend holds none of the manifest's groups", f"rebuild it: lune run kit asset {name}")
    for o in sc.objects:  # only the model: no helpers, lights or old cameras of the build
        if o.type in ("MESH", "CURVE", "LIGHT") and o not in objs.values():
            o.hide_render = True
    rbx.Asset._studio(types.SimpleNamespace(scene=sc, collection=sc.collection), list(objs.values()), (0.035, 0.037, 0.042),
                      look="product")
    import rbx_parts  # noqa: PLC0415  (P.gem's stones: refracting glass in the showcase, the baked colour in game)

    gem_faces = rbx_parts.glass_gems(list(objs.values()))
    sc.render.engine = "CYCLES"
    device = rbx.cycles_device(sc)
    sc.cycles.samples = a["samples"]
    sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = a["size"]
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = False
    sc.render.image_settings.file_format = "PNG"
    rest = {g: o.matrix_world.copy() for g, o in objs.items()}
    joints = {n: j for n, j in (man.get("joints") or {}).items() if j.get("kind") != "fixed" and j.get("group") in objs}
    by_group = {j["group"]: j for j in joints.values()}

    def pose(state):
        for g, o in objs.items():
            m = Matrix.Identity(4)
            for gg in rbx_mech._chain(by_group, g):  # (the root's joint first: a part riding on another moves with it)
                m = m @ rbx_mech.pose(by_group[gg], state[by_group[gg]["name"]])
            o.matrix_world = m @ rest[g]
        bpy.context.view_layer.update()

    def bounds():
        cs = [o.matrix_world @ Vector(c) for o in objs.values() for c in o.bound_box]
        return (Vector([min(c[i] for c in cs) for i in range(3)]), Vector([max(c[i] for c in cs) for i in range(3)]))

    frames, marks = timeline(joints)
    lo, hi = bounds()
    for st in frames:  # frame the whole motion: every extreme of the timeline inside the shot
        pose(st)
        l2, h2 = bounds()
        lo = Vector([min(lo[i], l2[i]) for i in range(3)])
        hi = Vector([max(hi[i], h2[i]) for i in range(3)])
    pose({n: j["min"] for n, j in joints.items()})
    cam = bpy.data.objects.new("ShowcaseCam", bpy.data.cameras.new("ShowcaseCam"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.data.lens = 50

    th = cam.data.sensor_width / 2 / cam.data.lens  # tan(half the horizontal field of view)
    tv = th * a["size"][1] / a["size"][0]

    def fit(points, direction, margin=1.1):
        """the camera along `direction`, as close as keeps every point in frame (perspective: by projection, not a
        bounding sphere — a long weapon in its sphere filled a third of the frame) -> (location, rotation, clips)"""
        d = direction.normalized()
        quat = (-d).to_track_quat("-Z", "Y")
        rm = quat.to_matrix()
        c0 = sum(points, Vector()) / len(points)
        q = [rm.inverted() @ (p_ - c0) for p_ in points]
        cx = (max(v.x for v in q) + min(v.x for v in q)) / 2
        cy = (max(v.y for v in q) + min(v.y for v in q)) / 2
        q = [v - Vector((cx, cy, 0)) for v in q]
        center = c0 + rm @ Vector((cx, cy, 0))
        dist = max(max(v.z + abs(v.x) * margin / th, v.z + abs(v.y) * margin / tv) for v in q)
        span = max((p_ - center).length for p_ in points)
        return center + d * dist, quat.to_euler(), max(1e-3, (dist - span) * 0.5), (dist + span) * 3

    def use(view):
        cam.location, cam.rotation_euler = view[0], view[1]
        cam.data.clip_start, cam.data.clip_end = view[2], view[3]

    def corners(group_names=None):
        return [o.matrix_world @ Vector(c) for g, o in objs.items() if group_names is None or g in group_names
                for c in o.bound_box]

    hero = rbx.BL_FROM_RBX @ Vector((-0.75, 0.42, -0.62))  # front-left, a little above (Roblox space -> Blender)
    t0 = time.time()
    # the turntable turns the MODEL under fixed lights (a camera orbit would sweep the light with it); one camera
    # that fits the model at every angle of the turn
    rest_pts = corners()
    tc = sum(rest_pts, Vector()) / len(rest_pts)
    up = rbx.BL_FROM_RBX @ Vector((0, 1, 0))
    spin = [Matrix.Translation(tc) @ Matrix.Rotation(2 * math.pi * k / 12, 4, up) @ Matrix.Translation(-tc) for k in range(12)]
    use(fit([m @ p_ for m in spin for p_ in rest_pts], hero, margin=1.03))
    turn = []
    for i in range(a["frames"]):
        rot = Matrix.Translation(tc) @ Matrix.Rotation(2 * math.pi * i / a["frames"], 4, up) @ Matrix.Translation(-tc)
        for g, o in objs.items():
            o.matrix_world = rot @ rest[g]
        bpy.context.view_layer.update()
        turn.append(shot(sc, os.path.join(out, f"turntable_{i:03d}.png")))
    for g, o in objs.items():
        o.matrix_world = rest[g]
    bpy.context.view_layer.update()
    # the mechanisms: each sequence gets a camera on ITS moving parts (padded to a quarter of the model, for context)
    # — a 14 degree trigger pull is invisible in a whole-weapon shot
    whole = fit(rest_pts, hero)
    model_span = max((hi - lo)[i] for i in range(3))
    views = [whole] * len(frames)
    for m in marks:
        focus = {joints[m["joint"]]["group"]} | {joints[t]["group"] for t in m["then"]}
        pts = []
        for k in range(m["frames"][0], m["frames"][1] + 1):
            pose(frames[k])
            pts += corners(focus)
        mid = sum(pts, Vector()) / len(pts)
        pad = model_span * 0.125
        pts += [mid + Vector(v) * pad for v in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))]
        # a part under the model's middle (a trigger in its guard, a folding leg) is seen from low on its side
        low = mid.z < (lo.z + hi.z) / 2 - model_span * 0.02
        close = fit(pts, rbx.BL_FROM_RBX @ Vector((-0.92, -0.12, -0.38)) if low else hero, margin=1.25)
        for k in range(m["frames"][0], m["frames"][1] + 1):
            views[k] = close
    mech = []
    for i, st in enumerate(frames):
        pose(st)
        use(views[i])
        mech.append(shot(sc, os.path.join(out, f"mechanism_{i:03d}.png")))
    info = {"asset": name, "turntable": turn, "mechanism": mech, "joints": marks, "device": device,
            "seconds": round(time.time() - t0, 1), "size": list(a["size"]), "samples": a["samples"],
            "gem_faces": gem_faces}
    with open(os.path.join(out, "showcase.json"), "w", encoding="utf-8") as fh:
        json.dump(info, fh, indent=1)
    moves = "; ".join(m["joint"] + (" then " + ", ".join(m["then"]) if m["then"] else "") for m in marks) or "no joints"
    return emit("pass", f"showcase {name}: a {len(turn)}-frame turntable and {len(mech)} mechanism frames ({moves}) in "
                f"{info['seconds']} s on {device}", f"look at build/showcase/{name}/ (the GIFs and poster come next)",
                showcase=os.path.join(out, "showcase.json"))


if __name__ == "__main__":
    code = main()
    sys.exit(code)
