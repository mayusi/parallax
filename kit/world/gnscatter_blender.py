"""kit world scatter-on - THINGS SCATTERED OVER A MESH'S SURFACE BY GEOMETRY NODES (run by Blender, background; the
owner's method list: "Geometry Nodes scattering", "Surface-based scattering").

    blender -b --factory-startup --python-exit-code 2 -P kit/world/gnscatter_blender.py -- <mesh>.mesh.json <out.json>
            --gap 3 [--seed 1] [--facing up|side|down|any] [--steep 0.5] [--most 400]

The kit's compiler scatters over the LAND (its heights). A mesh - a cliff, a rock, a wall, a roof - has a surface the
compiler cannot read: overhangs, ledges, faces. Blender can: a Geometry Nodes tree (Distribute Points on Faces, Poisson
disk) is built here from Python on the mesh `kit world meshes` made, evaluated, and its points and their surface
normals are read back and written as data. The compiler then sets things down on them (a mesh step's "on": ...).

  --gap     studs between two points at least (the Poisson disk's distance)
  --facing  which faces take points: up (floors, ledges, tops), side (walls), down (undersides), any. The faces that
            do not face that way are left out BEFORE the points are spread (they take none and thin none). A face that
            leans between two facings counts for both (at --steep 0.5 a slope of 30 to 60 degrees is up and side).
  --steep   how far a face may lean from that facing, as the normal's share along it (0.5 = within 60 degrees)
  --most    more points than this is an error (said, never cut silently); a mesh whose faces would take far more is
            refused before Blender spreads anything

<mesh>.mesh.json is the viewer's copy kit world meshes writes (positions, Roblox space, y up). The points are in the
SAME space: the mesh's own, in studs, as the registry measures it.
out.json: {"points": [{"pos": [x, y, z], "normal": [x, y, z]}], "gap", "seed", "facing", "steep", "source", "tris",
"min": [x, y, z], "size": [x, y, z] (the mesh's box: the compiler refuses points made on another build of it)}
A run that fails REMOVES the points an earlier run wrote there (stale points are not left to be built), and says so.
The last line printed is a JSON verdict: {"status": "pass" | "fail", "summary", "next_action"}."""
import base64
import json
import math
import os
import struct
import sys

FACINGS = ("up", "side", "down", "any")
PACKED = 0.6  # points a square of the gap's side takes, about, when a surface is filled by a Poisson disk


def arguments(argv):
    """-> (settings, None) or (None, why)"""
    if len(argv) < 2:
        return None, "usage: <mesh>.mesh.json <out.json> --gap <studs> [--seed n] [--facing up|side|down|any] [--steep 0..1] [--most n]"
    s = {"source": argv[0], "out": argv[1], "gap": None, "seed": 1, "facing": "any", "steep": 0.5, "most": 400}
    k = 2
    while k < len(argv):
        word = argv[k]
        if word not in ("--gap", "--seed", "--facing", "--steep", "--most") or k + 1 >= len(argv):
            return None, f"scatter-on: {word} is not a word it knows (--gap, --seed, --facing, --steep, --most), or has no value"
        value = argv[k + 1]
        k += 2
        if word == "--facing":
            if value not in FACINGS:
                return None, f"scatter-on: --facing is one of {', '.join(FACINGS)} (got {value})"
            s["facing"] = value
            continue
        try:
            number = float(value)
        except ValueError:
            return None, f"scatter-on: {word} is a number (got {value})"
        if number != number or number in (math.inf, -math.inf):
            return None, f"scatter-on: {word} is a number (got {value})"
        s[word[2:]] = number
    if s["gap"] is None:
        return None, "scatter-on: --gap says how many studs lie between two points at least"
    if not 0.5 <= s["gap"] <= 200:
        return None, f"scatter-on: --gap is 0.5 to 200 studs (got {s['gap']:g})"
    if s["seed"] % 1 != 0 or not 0 <= s["seed"] <= 65535:
        return None, f"scatter-on: --seed is a whole number 0 to 65535 (got {s['seed']:g})"
    if not 0 <= s["steep"] < 1:
        return None, f"scatter-on: --steep is 0 (any lean) to under 1 (got {s['steep']:g})"
    if s["most"] % 1 != 0 or not 1 <= s["most"] <= 4000:
        return None, f"scatter-on: --most is a whole number 1 to 4000 (got {s['most']:g})"
    s["seed"], s["most"] = int(s["seed"]), int(s["most"])
    return s, None


def triangles(path):
    """the viewer's copy of a mesh -> [(x, y, z)] three a triangle, Roblox space; or (None, why)"""
    try:
        data = json.load(open(path, encoding="utf-8"))
        raw = base64.b64decode(data["position"])
    except (OSError, ValueError, KeyError, TypeError) as e:
        return None, f"scatter-on: {path} is no mesh copy of kit world meshes ({type(e).__name__})"
    n = len(raw) // 4
    if n < 9 or n % 9 != 0:
        return None, f"scatter-on: {path} holds no whole triangles"
    flat = struct.unpack(f"<{n}f", raw[: n * 4])
    return [flat[i:i + 3] for i in range(0, n, 3)], None


def keeps(normal, facing, steep):
    """does a face with this normal (Roblox space, y up) take points"""
    if facing == "up":
        return normal[1] >= steep
    if facing == "down":
        return normal[1] <= -steep
    if facing == "side":
        return math.hypot(normal[0], normal[2]) >= steep and abs(normal[1]) <= math.sqrt(max(0.0, 1 - steep * steep))
    return True


def to_blender(p):
    """a place or a direction, Roblox (x, y up, z) -> Blender (x, y, z up): a quarter turn about x, no mirror"""
    return (p[0], -p[2], p[1])


def to_roblox(p):
    """... and back: Blender (x, y, z up) -> Roblox (x, y up, z)"""
    return (p[0], p[2], -p[1])


def face(a, b, c):
    """a triangle's unit normal (by its winding, as the mesh copy has it) and its area -> (normal, area); a triangle of
    no area has the normal (0, 0, 0)"""
    u = [b[i] - a[i] for i in range(3)]
    v = [c[i] - a[i] for i in range(3)]
    n = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]
    length = math.sqrt(sum(x * x for x in n))
    if length <= 1e-12:
        return (0.0, 0.0, 0.0), 0.0
    return tuple(x / length for x in n), length / 2


def survey(tris, facing, steep):
    """the mesh as the scatter needs it -> {"keep": [does each triangle take points], "area": the area of those that
    do, "min": [x, y, z], "size": [x, y, z] (its box)}"""
    keep, area = [], 0.0
    for i in range(0, len(tris), 3):
        normal, a = face(tris[i], tris[i + 1], tris[i + 2])
        ok = a > 0 and keeps(normal, facing, steep)
        keep.append(ok)
        area += a if ok else 0.0
    lo = [min(p[k] for p in tris) for k in range(3)]
    hi = [max(p[k] for p in tris) for k in range(3)]
    return {"keep": keep, "area": area, "min": [round(v, 4) for v in lo], "size": [round(hi[k] - lo[k], 4) for k in range(3)]}


def expected(area, gap):
    """about how many points a surface of that area takes at that gap"""
    return PACKED * area / (gap * gap)


def too_many(area, s):
    """is the mesh refused before anything is spread: its faces would take far more points than --most -> why | None"""
    about = expected(area, s["gap"])
    if about > s["most"] * 1.5:
        return (f"scatter-on: about {int(about)} points at a gap of {s['gap']:g} on {area:.0f} sq studs of faces that face "
                f"{s['facing']} - far over the most asked ({s['most']}): a wider --gap, a narrower --facing, or a higher --most")
    return None


def scatter(tris, keep, s):
    """THE SCATTER, in Blender: the triangles as a mesh, a Geometry Nodes tree on it, its points read back.
    -> [{"pos", "normal"}] in Roblox space"""
    import bpy

    bpy.ops.wm.read_factory_settings(use_empty=True)
    me = bpy.data.meshes.new("surface")
    me.from_pydata([to_blender(p) for p in tris], [], [(i, i + 1, i + 2) for i in range(0, len(tris), 3)])
    me.update()
    # which faces take points: a face attribute, read by the node's Selection - so the faces left out take no points
    # AND thin none of the others (filtered afterwards, the far side of a thin wall starved the near side)
    chosen = me.attributes.new("kit_keep", "BOOLEAN", "FACE")
    for i, ok in enumerate(keep):
        chosen.data[i].value = bool(ok)
    obj = bpy.data.objects.new("surface", me)
    bpy.context.scene.collection.objects.link(obj)
    ng = bpy.data.node_groups.new("KitScatter", "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    nin, nout = ng.nodes.new("NodeGroupInput"), ng.nodes.new("NodeGroupOutput")
    pick = ng.nodes.new("GeometryNodeInputNamedAttribute")
    pick.data_type = "BOOLEAN"
    pick.inputs["Name"].default_value = "kit_keep"
    dist = ng.nodes.new("GeometryNodeDistributePointsOnFaces")
    dist.distribute_method = "POISSON"
    dist.inputs["Distance Min"].default_value = s["gap"]
    # (the Poisson disk thins a first throw down to the gap; the throw is ten points a gap squared - the node keeps
    # about 0.6 a gap squared of them on an open face, fewer on a mesh of small faces: it is a spread, not a packing)
    dist.inputs["Density Max"].default_value = 10.0 / (s["gap"] * s["gap"])
    dist.inputs["Seed"].default_value = s["seed"]
    store = ng.nodes.new("GeometryNodeStoreNamedAttribute")
    store.data_type = "FLOAT_VECTOR"
    store.domain = "POINT"
    store.inputs["Name"].default_value = "kit_normal"
    to_verts = ng.nodes.new("GeometryNodePointsToVertices")
    ng.links.new(nin.outputs[0], dist.inputs["Mesh"])
    ng.links.new(pick.outputs[0], dist.inputs["Selection"])
    ng.links.new(dist.outputs["Points"], store.inputs["Geometry"])
    ng.links.new(dist.outputs["Normal"], store.inputs["Value"])
    ng.links.new(store.outputs[0], to_verts.inputs[0])
    ng.links.new(to_verts.outputs[0], nout.inputs[0])
    mod = obj.modifiers.new("scatter", "NODES")
    mod.node_group = ng
    ev = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    out_mesh = ev.to_mesh()
    normals = out_mesh.attributes.get("kit_normal")
    points = []
    for i, v in enumerate(out_mesh.vertices):
        normal = list(to_roblox(normals.data[i].vector if normals else (0.0, 0.0, 1.0)))
        length = math.sqrt(sum(c * c for c in normal)) or 1.0
        normal = [c / length for c in normal]
        if keeps(normal, s["facing"], s["steep"]):
            points.append({"pos": [round(c, 4) for c in to_roblox(v.co)], "normal": [round(c, 5) for c in normal]})
    ev.to_mesh_clear()
    return points


def judged(count, s):
    """what a run's count of points comes to -> why it fails | None"""
    if count > s["most"]:
        return (f"scatter-on: {count} points, over the most asked ({s['most']}): a wider --gap, a narrower --facing, "
                "or a higher --most")
    if count == 0:
        return (f"scatter-on: no point - no face of this mesh faces {s['facing']} within --steep {s['steep']:g}, or the "
                "gap is wider than the mesh")
    return None


def fail(why, out=None):
    """a failed run: the points an earlier run wrote there are removed (they are not left to be built), and it is said"""
    if out and os.path.isfile(out):
        os.remove(out)
        why += f" (the earlier points in {os.path.basename(out)} were removed)"
    print(json.dumps({"status": "fail", "summary": why, "next_action": why}))
    sys.exit(1)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    s, why = arguments(argv)
    if why:
        fail(why)
    tris, why = triangles(s["source"])
    if why:
        fail(why, s["out"])
    seen = survey(tris, s["facing"], s["steep"])
    why = too_many(seen["area"], s)
    if why:
        fail(why, s["out"])
    points = scatter(tris, seen["keep"], s) if seen["area"] > 0 else []
    why = judged(len(points), s)
    if why:
        fail(why, s["out"])
    os.makedirs(os.path.dirname(os.path.abspath(s["out"])), exist_ok=True)
    with open(s["out"], "w", encoding="utf-8") as fh:
        json.dump({"points": points, "gap": s["gap"], "seed": s["seed"], "facing": s["facing"], "steep": s["steep"],
                   "source": os.path.basename(s["source"]), "tris": len(tris) // 3, "min": seen["min"],
                   "size": seen["size"]}, fh)
    summary = f"scatter-on: {len(points)} points on {os.path.basename(s['source'])} ({s['facing']}, gap {s['gap']:g}) -> {s['out']}"
    print(json.dumps({"status": "pass", "summary": summary, "next_action": "name the points in a mesh step's \"on\""}))


if __name__ == "__main__":
    main()
