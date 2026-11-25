"""2026-10-24: kit/anim/export_clip.py writes an R6 clip as a glTF 2.0 binary other engines load - six rigid part nodes
(plus the blade of a sword clip) animated by their world transforms, the root travel composed in, quaternions without
sign flips, boxes facing outward. (Blender re-imports KatanaKaeshi.glb to 0.0000 studs of the kit's FK.)"""
import math
import os
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "anim"))
import clip as C  # noqa: E402
import export_clip as X  # noqa: E402

JOINTS = ["Torso", "Head", "Right Arm", "Left Arm", "Right Leg", "Left Leg"]


def probe(n=20, sword=True, root=True):
    def arm(i):
        a = math.radians(12 * i)                         # the right arm swings 228 deg about X (past 180: the
        #                                                  matrix -> quaternion sign flips there)
        return [math.sin(a / 2), 0.0, 0.0, math.cos(a / 2), 0.0, 0.0, 0.0]
    c = {"name": "Probe", "rig": "R6", "fps": 60, "times": [i / 60 for i in range(n)],
         "joints": {j: {"frames": [arm(i) if j == "Right Arm" else [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]
                                   for i in range(n)]} for j in JOINTS}}
    if root:
        c["root"] = [[0.0, 0.0, 0.0, 1.0, 0.0, 0.0, -0.2 * i] for i in range(n)]
    if sword:
        c["sword"] = {"tip": [[1.5, -1.0, -2.0 - 0.05 * i] for i in range(n)],
                      "grip_path": [[1.5, -1.0, -1.0 - 0.05 * i] for i in range(n)], "length": 3.6, "grip": 0.5}
    return c


def accessor(doc, blob, k):
    acc = doc["accessors"][k]
    view = doc["bufferViews"][acc["bufferView"]]
    comps = {"SCALAR": 1, "VEC3": 3, "VEC4": 4}[acc["type"]]
    fmt = "f" if acc["componentType"] == 5126 else "H"
    vals = struct.unpack_from(f"<{acc['count'] * comps}{fmt}", blob, view["byteOffset"])
    return np.asarray(vals).reshape(acc["count"], comps) if comps > 1 else np.asarray(vals)


def test_the_glb_carries_every_part_and_the_blade_on_the_kits_fk(tmp_path):
    c = probe()
    path = str(tmp_path / "Probe.glb")
    info = X.glb(c, C.load_rig("r6"), path)
    doc, blob = X.read_glb(path)
    names = [nd["name"] for nd in doc["nodes"]]
    assert set(JOINTS + ["Sword"]) <= set(names) and info["frames"] == 20
    W = C.world_frames(c, C.load_rig("r6"))
    anim = doc["animations"][0]
    for ch in anim["channels"]:
        node = doc["nodes"][ch["target"]["node"]]["name"]
        s = anim["samplers"][ch["sampler"]]
        times, vals = accessor(doc, blob, s["input"]), accessor(doc, blob, s["output"])
        assert len(times) == 20 and abs(times[-1] - 19 / 60) < 1e-6
        if ch["target"]["path"] == "translation" and node != "Sword":
            assert np.allclose(vals[13], W[13][node][:3, 3], atol=1e-5)        # the root travel is composed in
        if ch["target"]["path"] == "rotation":
            assert all(float(vals[i] @ vals[i + 1]) >= 0 for i in range(19))   # no sign flip between frames
            if node != "Sword":
                for i in (0, 9, 16):                                            # the rotation IS the kit's FK
                    assert np.allclose(C.quat_mat(list(vals[i])), W[i][node][:3, :3], atol=1e-5)
    sw = next(i for i, nd in enumerate(doc["nodes"]) if nd["name"] == "Sword")
    ch = next(c_ for c_ in anim["channels"] if c_["target"] == {"node": sw, "path": "translation"})
    mid = accessor(doc, blob, anim["samplers"][ch["sampler"]]["output"])[5]
    # the whole sword's centre: from the pommel (grip - spacing / 2) to the tip -> grip + d (length / 2 - spacing / 2)
    # (grip z -1.25, d = -Z, 1.8 - 0.25), moved by the root (-1.0)
    assert np.allclose(mid, [1.5, -1.0, -1.25 - 1.55 - 1.0], atol=1e-5)
    rch = next(c_ for c_ in anim["channels"] if c_["target"] == {"node": sw, "path": "rotation"})
    q = accessor(doc, blob, anim["samplers"][rch["sampler"]]["output"])[5]
    assert np.allclose(C.quat_mat(list(q))[:, 1], [0.0, 0.0, -1.0], atol=1e-6)    # its +Y runs grip -> tip
    for m in doc["meshes"]:
        prim = m["primitives"][0]
        pa = doc["accessors"][prim["attributes"]["POSITION"]]
        assert "min" in pa and "max" in pa                                       # (required by the spec)
        assert doc["bufferViews"][doc["accessors"][prim["indices"]]["bufferView"]]["target"] == 34963


def test_a_clip_without_a_sword_has_no_blade_and_boxes_face_outward(tmp_path):
    path = str(tmp_path / "Plain.glb")
    X.glb(probe(sword=False, root=False), C.load_rig("r6"), path)
    doc, blob = X.read_glb(path)
    assert "Sword" not in [nd["name"] for nd in doc["nodes"]]
    prim = doc["meshes"][0]["primitives"][0]
    pos, nrm = accessor(doc, blob, prim["attributes"]["POSITION"]), accessor(doc, blob, prim["attributes"]["NORMAL"])
    idx = accessor(doc, blob, prim["indices"]).astype(int)
    for k in range(0, len(idx), 3):
        a, b, c = pos[idx[k]], pos[idx[k + 1]], pos[idx[k + 2]]
        assert float(np.cross(b - a, c - a) @ nrm[idx[k]]) > 0


def test_a_glb_that_is_not_one_is_refused(tmp_path):
    p = tmp_path / "bad.glb"
    p.write_bytes(b"not a glb at all")
    try:
        X.read_glb(str(p))
    except (ValueError, struct.error):
        return
    raise AssertionError("a broken file was read as a glb")


def test_a_cutscene_puts_every_actor_on_one_clock_and_hides_its_gaps(tmp_path):
    path = str(tmp_path / "Duel.glb")
    vis = [True] * 20
    vis[5] = vis[6] = False
    info = X.glb_actors({"shade": (probe(), "shadow", vis), "ronin": (probe(sword=False), "noob")},
                        C.load_rig("r6"), path, "Duel")
    doc, blob = X.read_glb(path)
    names = [nd["name"] for nd in doc["nodes"]]
    assert "shade Sword" in names and "ronin Torso" in names and "ronin Sword" not in names
    assert len(doc["animations"]) == 1 and info["frames"] == 20
    shade = names.index("shade")
    ch = [c for c in doc["animations"][0]["channels"] if c["target"] == {"node": shade, "path": "scale"}]
    assert len(ch) == 1
    s = doc["animations"][0]["samplers"][ch[0]["sampler"]]
    scale = accessor(doc, blob, s["output"])
    assert s["interpolation"] == "STEP" and scale[5].tolist() == [0, 0, 0] and scale[7].tolist() == [1, 1, 1]
    assert not any(c["target"]["path"] == "scale" and c["target"]["node"] == names.index("ronin")
                   for c in doc["animations"][0]["channels"])                     # (never hidden: no scale track)
    torso = {m["name"]: m["pbrMetallicRoughness"]["baseColorFactor"] for m in doc["materials"]}
    assert torso["shade Torso"] != torso["ronin Torso"]                           # each actor its own look


def test_the_gltf_json_is_the_same_scene_with_its_buffer_inside(tmp_path):
    import base64
    import json
    glb_path = str(tmp_path / "P.glb")
    X.glb(probe(), C.load_rig("r6"), glb_path)
    out = X.gltf_json(glb_path, str(tmp_path / "P.gltf"))
    doc = json.load(open(out, encoding="utf-8"))
    d2, blob = X.read_glb(glb_path)
    uri = doc["buffers"][0]["uri"]
    assert uri.startswith("data:application/octet-stream;base64,")
    assert base64.b64decode(uri.split(",", 1)[1]) == blob and doc["nodes"] == d2["nodes"]


def test_continuous_undoes_quaternion_sign_flips():
    """q and -q are one rotation; a LINEAR player between them spins the long way round"""
    qs = [[0.0, 0.0, 0.0, 1.0], [-0.1, 0.0, 0.0, -0.995], [0.2, 0.0, 0.0, 0.98], [-0.3, 0.0, 0.0, -0.954]]
    out = X.continuous(qs)
    assert all(float(np.dot(out[i], out[i + 1])) > 0 for i in range(3))
    assert all(np.allclose(np.abs(o), np.abs(q)) for o, q in zip(out, qs))      # the same rotations


def test_a_cutscene_carries_its_planned_camera_looking_at_its_target(tmp_path):
    path = str(tmp_path / "Shot.glb")
    cam = [{"loc": [10.0, 4.0, 5.0 - 0.1 * i], "target": [0.0, 1.0, 0.0]} for i in range(20)]
    X.glb_actors({"a": (probe(sword=False), "noob")}, C.load_rig("r6"), path, "Shot", camera=cam)
    doc, blob = X.read_glb(path)
    assert doc["cameras"][0]["type"] == "perspective"
    node = next(i for i, nd in enumerate(doc["nodes"]) if nd.get("camera") == 0)
    anim = doc["animations"][0]
    ch = {c["target"]["path"]: c for c in anim["channels"] if c["target"]["node"] == node}
    loc = accessor(doc, blob, anim["samplers"][ch["translation"]["sampler"]]["output"])
    rot = accessor(doc, blob, anim["samplers"][ch["rotation"]["sampler"]]["output"])
    for i in (0, 10, 19):
        assert np.allclose(loc[i], cam[i]["loc"], atol=1e-5)
        forward = -C.quat_mat(list(rot[i]))[:, 2]                                 # a glTF camera looks down -Z
        want = np.asarray(cam[i]["target"]) - np.asarray(cam[i]["loc"])
        assert float(forward @ (want / np.linalg.norm(want))) > 0.9999


def test_a_camera_key_with_no_direction_keeps_the_last_one():
    q0 = X.look_quat([10.0, 4.0, 5.0], [0.0, 1.0, 0.0])
    assert X.look_quat([1.0, 1.0, 1.0], [1.0, 1.0, 1.0], q0) == q0
    assert X.look_quat([1.0, 1.0, 1.0], [1.0, 1.0, 1.0]) == [0.0, 0.0, 0.0, 1.0]
