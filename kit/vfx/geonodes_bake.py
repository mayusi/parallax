"""geonodes_bake.py - run INSIDE Blender by kit/vfx/geonodes.py (never by hand):

    blender -b --factory-startup --python-exit-code 2 -P kit/vfx/geonodes_bake.py -- <asks.json> <out.json>

Builds a GEOMETRY NODES tree for the asked recipe on an empty scene, steps the scene's frames, reads the evaluated
mesh of every frame and writes them as JSON: {"blender", "nodes": [the tree's node types], "cols", "rows", "strips",
"frames": [[x, y, z, ...]]} in the kit's axes (y up) and the mesh sequence's vertex order. The tree IS the effect:
nothing here moves a vertex in Python.

  ripple   a Grid whose points a Set Position node lifts by a ring wave that travels out from the middle with the
           Scene Time, dying toward the rim
  scatter  points Distributed on the Faces of a disc, a small quad Instanced on each, every instance scaled up (from a fiftieth of
           its size) as a front that travels out from the middle reaches it and turned by the Scene Time; Realized: one strip a quad (as many as the tree gives points)
"""
import json
import math
import sys

import bpy


def link(tree, a, b):
    tree.links.new(a, b)


def node(tree, kind, **props):
    n = tree.nodes.new(kind)
    for k, v in props.items():
        setattr(n, k, v)
    return n


def maths(tree, op, a=None, b=None):
    n = node(tree, "ShaderNodeMath", operation=op)
    for i, v in enumerate((a, b)):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            n.inputs[i].default_value = float(v)
        else:
            link(tree, v, n.inputs[i])
    return n.outputs[0]


def new_tree(name):
    tree = bpy.data.node_groups.new(name, "GeometryNodeTree")
    tree.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    out = node(tree, "NodeGroupOutput")
    return tree, out


def seconds(tree):
    return node(tree, "GeometryNodeInputSceneTime").outputs["Seconds"]


def ripple(a):
    tree, out = new_tree("kit_ripple")
    grid = node(tree, "GeometryNodeMeshGrid")
    grid.inputs["Size X"].default_value = grid.inputs["Size Y"].default_value = 1.0
    grid.inputs["Vertices X"].default_value = a["cols"] + 1
    grid.inputs["Vertices Y"].default_value = a["rows"] + 1
    pos = node(tree, "GeometryNodeInputPosition").outputs[0]
    dist = node(tree, "ShaderNodeVectorMath", operation="LENGTH")
    link(tree, pos, dist.inputs[0])
    r = dist.outputs["Value"]
    # height = amount * sin(2 pi (r * waves - t * speed)) * (1 - 2 r)^+ : rings that run out and die at the rim
    phase = maths(tree, "SUBTRACT", maths(tree, "MULTIPLY", r, a["waves"]), maths(tree, "MULTIPLY", seconds(tree), a["speed"]))
    wave = maths(tree, "SINE", maths(tree, "MULTIPLY", phase, 2 * math.pi))
    fade = maths(tree, "MAXIMUM", maths(tree, "SUBTRACT", 1.0, maths(tree, "MULTIPLY", r, 2.0)), 0.0)
    height = maths(tree, "MULTIPLY", maths(tree, "MULTIPLY", wave, fade), a["amount"])
    lift = node(tree, "ShaderNodeCombineXYZ")
    link(tree, height, lift.inputs["Z"])
    move = node(tree, "GeometryNodeSetPosition")
    link(tree, grid.outputs["Mesh"], move.inputs["Geometry"])
    link(tree, lift.outputs[0], move.inputs["Offset"])
    link(tree, move.outputs["Geometry"], out.inputs[0])
    return tree, a["cols"], a["rows"], 1


def scatter(a):
    tree, out = new_tree("kit_scatter")
    disc = node(tree, "GeometryNodeMeshCircle", fill_type="NGON")
    disc.inputs["Vertices"].default_value = 48
    disc.inputs["Radius"].default_value = 0.5
    spread = node(tree, "GeometryNodeDistributePointsOnFaces", distribute_method="RANDOM")
    spread.inputs["Density"].default_value = a["count"] / (math.pi * 0.25)  # (about `count` points: what the tree gives is kept)
    spread.inputs["Seed"].default_value = a["seed"]
    link(tree, disc.outputs["Mesh"], spread.inputs["Mesh"])
    index = node(tree, "GeometryNodeInputIndex").outputs[0]
    quad = node(tree, "GeometryNodeMeshGrid")
    quad.inputs["Size X"].default_value = quad.inputs["Size Y"].default_value = a["size"]
    quad.inputs["Vertices X"].default_value = quad.inputs["Vertices Y"].default_value = 2
    pos = node(tree, "GeometryNodeInputPosition").outputs[0]
    dist = node(tree, "ShaderNodeVectorMath", operation="LENGTH")
    link(tree, pos, dist.inputs[0])
    # a front runs out from the middle: an instance is nothing before it comes, full size `rise` of a radius after
    front = maths(tree, "MULTIPLY", seconds(tree), a["speed"])
    grown = node(tree, "ShaderNodeClamp")
    grown.inputs["Min"].default_value = 0.02  # (never NOTHING: a mesh whose first frame is all points of no size has no triangle to build from)
    link(tree, maths(tree, "DIVIDE", maths(tree, "SUBTRACT", front, dist.outputs["Value"]), a["rise"]), grown.inputs["Value"])
    turn = node(tree, "ShaderNodeCombineXYZ")
    link(tree, maths(tree, "ADD", maths(tree, "MULTIPLY", seconds(tree), a["spin"]), maths(tree, "MULTIPLY", index, 2.399963)), turn.inputs["Z"])
    place = node(tree, "GeometryNodeInstanceOnPoints")
    link(tree, spread.outputs["Points"], place.inputs["Points"])
    link(tree, quad.outputs["Mesh"], place.inputs["Instance"])
    link(tree, turn.outputs[0], place.inputs["Rotation"])
    size = node(tree, "ShaderNodeCombineXYZ")
    for axis in ("X", "Y", "Z"):
        link(tree, grown.outputs[0], size.inputs[axis])
    link(tree, size.outputs[0], place.inputs["Scale"])
    real = node(tree, "GeometryNodeRealizeInstances")
    link(tree, place.outputs["Instances"], real.inputs["Geometry"])
    link(tree, real.outputs["Geometry"], out.inputs[0])
    return tree, 1, 1, None  # (as many strips as the tree gives points)


RECIPES = {"ripple": ripple, "scatter": scatter}


def grid_order(cols, rows):
    """which of a Mesh Grid node's vertices is the sequence's vertex (row j, column i): read from a plain grid's own
    coordinates, not assumed"""
    tree, out = new_tree("kit_order")
    grid = node(tree, "GeometryNodeMeshGrid")
    grid.inputs["Vertices X"].default_value = cols + 1
    grid.inputs["Vertices Y"].default_value = rows + 1
    link(tree, grid.outputs["Mesh"], out.inputs[0])
    pts = evaluated(holder("kit_order_obj", tree))
    order = {}
    for k, (x, y, z) in enumerate(pts):
        order[(round((y + 0.5) * rows), round((x + 0.5) * cols))] = k
    return [order[(j, i)] for j in range(rows + 1) for i in range(cols + 1)]


def holder(name, tree):
    mesh = bpy.data.meshes.new(name)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    mod = obj.modifiers.new("kit", "NODES")
    mod.node_group = tree
    return obj


def evaluated(obj):
    deps = bpy.context.evaluated_depsgraph_get()
    deps.update()
    mesh = obj.evaluated_get(deps).to_mesh()
    pts = [tuple(v.co) for v in mesh.vertices]
    obj.evaluated_get(deps).to_mesh_clear()
    return pts


def main():
    asks_path, out_path = sys.argv[sys.argv.index("--") + 1:][:2]
    with open(asks_path, encoding="utf-8") as fh:
        a = json.load(fh)
    scene = bpy.context.scene
    scene.render.fps = a["fps"]
    tree, cols, rows, strips = RECIPES[a["recipe"]](a)
    order = grid_order(cols, rows)
    obj = holder("kit_geonodes", tree)
    per = (cols + 1) * (rows + 1)
    frames = []
    for f in range(a["frames"]):
        scene.frame_set(f + 1)
        pts = evaluated(obj)
        if strips is None:
            strips = len(pts) // per
        if strips < 1 or len(pts) != per * strips:
            raise SystemExit(f"frame {f + 1}: the tree gave {len(pts)} points, {per * strips} were to be there (a mesh sequence keeps its points)")
        flat = []
        for s in range(strips):
            for k in order:
                x, y, z = pts[s * per + k]
                flat.extend([round(x, 4), round(z, 4), round(-y, 4)])  # Blender's z up -> the kit's y up
        frames.append(flat)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump({"blender": bpy.app.version_string, "nodes": sorted({n.bl_idname for n in tree.nodes}), "cols": cols, "rows": rows, "strips": strips,
                   "frames": frames}, fh)


main()
