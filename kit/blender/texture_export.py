"""texture_export.py — an asset's last full build as ONE mesh file, for TRELLIS.2 to paint (lune run kit gen texture).

    blender -b --factory-startup build/models/<name>.blend --python-exit-code 2 -P kit/blender/texture_export.py --
        <name> <out.ply> [--group <group>]

Every group of the build (or the one asked for) as it was baked — joined, transforms applied — written in the kit's
own space: Roblox studs, Y up, -Z front (Blender's world through BL_FROM_RBX's inverse). That is the frame a glTF
file uses, so the textured GLB that comes back is placed by Blender's glTF import (Y up -> Z up, the same turn as
BL_FROM_RBX) exactly where the asset's parts are built, and a.texture_from(...) bakes it straight onto them.
Beside the PLY: <out>.json — what was exported (groups, triangles, size, the build's id). One JSON verdict line.
"""

import json
import os
import sys

import bpy
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rbx_texture  # noqa: E402
from rbx import BL_FROM_RBX, EXPORTS, _rel  # noqa: E402


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))


def main(argv):
    if len(argv) < 2:
        return emit("fail", "texture export: usage: texture_export.py -- <name> <out.ply> [--group <group>]",
                    "lune run kit gen texture <asset> --image <picture>")
    name, out = argv[0], argv[1]
    group = argv[argv.index("--group") + 1] if "--group" in argv else None
    try:
        with open(os.path.join(EXPORTS, f"{name}.manifest.json"), encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, ValueError):
        return emit("fail", f"texture export: {name} has no full build (no build/models/{name}.manifest.json)",
                    f"build it first: lune run kit asset {name}")
    groups = list(manifest.get("groups") or {})
    if group is not None and group not in groups:
        return emit("fail", f"texture export: {name} has no group '{group}' (groups: {', '.join(groups)})",
                    f"lune run kit gen texture {name} --image <picture> [--group {'|'.join(groups)}]")
    chosen = [group] if group else groups
    to_rbx = BL_FROM_RBX.inverted()
    verts, tris, objects, offset = [], [], [], 0
    deps = bpy.context.evaluated_depsgraph_get()
    for g in chosen:
        oname = name if g == "main" else f"{name}_{g}"
        obj = bpy.data.objects.get(oname)
        if obj is None or obj.type != "MESH":
            return emit("fail", f"texture export: the build of {name} has no mesh '{oname}'",
                        f"build it again: lune run kit asset {name}")
        ev = obj.evaluated_get(deps)
        me = ev.to_mesh()
        me.calc_loop_triangles()
        co = np.empty(len(me.vertices) * 3, np.float32)
        me.vertices.foreach_get("co", co)
        m = np.array(to_rbx @ obj.matrix_world, dtype=np.float64)
        verts.append(co.reshape(-1, 3).astype(np.float64) @ m[:3, :3].T + m[:3, 3])
        tri = np.empty(len(me.loop_triangles) * 3, np.int32)
        me.loop_triangles.foreach_get("vertices", tri)
        tris.append(tri.reshape(-1, 3).astype(np.int64) + offset)
        offset += len(me.vertices)
        objects.append(oname)
        ev.to_mesh_clear()
    v, t = np.concatenate(verts), np.concatenate(tris)
    if not len(t):
        return emit("fail", f"texture export: {', '.join(objects)} has no faces", f"lune run kit asset {name}")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    rbx_texture.write_ply(out, v, t)
    lo, hi = v.min(axis=0), v.max(axis=0)
    info = {"asset": name, "groups": chosen, "objects": objects, "vertices": int(len(v)), "triangles": int(len(t)),
            "size_studs": [round(float(x), 4) for x in hi - lo],
            "center_studs": [round(float(x), 4) for x in (lo + hi) / 2],
            "build_id": manifest.get("build_id"), "stage": manifest.get("stage", "game"),
            "space": "roblox studs, Y up, -Z front (glTF's frame: Blender's glTF import puts it back exactly)"}
    with open(os.path.splitext(out)[0] + ".json", "w", encoding="utf-8") as fh:
        json.dump(info, fh, indent=1)
    return emit("pass", f"texture export: {', '.join(objects)} -> {_rel(out)} ({len(t)} triangles, "
                        f"{' x '.join(str(x) for x in info['size_studs'])} studs)",
                "none — proceed", out=_rel(out), info=info)


main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
