"""rbx_sdfnodes.py — Blender's OWN distance-field nodes (OpenVDB level sets in Geometry Nodes, Blender 5.x) as a fuse:
overlapping parts — kitbashed, imported, CAD — welded into ONE watertight mesh, with sharp boolean cuts and real
fillets where they meet (SDF Grid Boolean / SDF Grid Fillet), at a chosen voxel size.

    import rbx_sdfnodes
    obj = rbx_sdfnodes.fuse("Body", [(a_obj, "UNION"), (b_obj, "UNION"), (hole_obj, "DIFFERENCE")],
                            voxel=0.0005, fillet=3)
"""

import bpy

OPS = ("UNION", "DIFFERENCE", "INTERSECT")


def fuse(name, parts, voxel, fillet=0, adaptivity=0.0, band=3):
    """parts: [(object, op)] in order, the first always the base (its op ignored); voxel: m; fillet: SDF Grid Fillet
    iterations (0: none — every join sharp); -> a new mesh object `name` (the inputs untouched, hidden from render)"""
    if not parts:
        raise ValueError("fuse: no parts")
    for _o, op in parts[1:]:
        if op not in OPS:
            raise ValueError(f'fuse: op "{op}" — one of {", ".join(OPS)}')
    ng = bpy.data.node_groups.new(f"{name}_fuse", "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    nodes, links = ng.nodes, ng.links
    nodes.new("NodeGroupInput")
    out = nodes.new("NodeGroupOutput")
    grid = None
    for i, (o, op) in enumerate(parts):
        info = nodes.new("GeometryNodeObjectInfo")
        info.inputs["Object"].default_value = o
        info.transform_space = "RELATIVE"
        sdf = nodes.new("GeometryNodeMeshToSDFGrid")
        sdf.inputs["Voxel Size"].default_value = float(voxel)
        sdf.inputs["Band Width"].default_value = int(band)
        links.new(info.outputs["Geometry"], sdf.inputs["Mesh"])
        if grid is None:
            grid = sdf.outputs["SDF Grid"]
            continue
        b = nodes.new("GeometryNodeSDFGridBoolean")
        b.operation = op
        sock = {s.identifier: s for s in b.inputs}
        # (union / intersect: ONE multi-input socket, identifier "Grid 2", takes every grid; difference: the base in
        #  "Grid 1", the cutters in "Grid 2" — the socket names change with the operation, the identifiers do not)
        links.new(grid, sock["Grid 1"] if op == "DIFFERENCE" else sock["Grid 2"])
        links.new(sdf.outputs["SDF Grid"], sock["Grid 2"])
        grid = b.outputs["Grid"]
    if fillet:
        f = nodes.new("GeometryNodeSDFGridFillet")
        f.inputs["Iterations"].default_value = int(fillet)
        links.new(grid, f.inputs["Grid"])
        grid = f.outputs["Grid"]
    m = nodes.new("GeometryNodeGridToMesh")
    m.inputs["Adaptivity"].default_value = float(adaptivity)
    m.inputs["Threshold"].default_value = 0.0   # (its default 0.1 is a DENSITY threshold: on an SDF in metres it asks
    #                                            for the surface 10 cm out — past the band, an empty mesh)
    links.new(grid, m.inputs["Grid"])
    links.new(m.outputs["Mesh"], out.inputs["Geometry"])
    # the host: an empty mesh carrying the modifier, then applied (a plain mesh comes out)
    me = bpy.data.meshes.new(name)
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    mod = obj.modifiers.new("Fuse", "NODES")
    mod.node_group = ng
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    new = bpy.data.meshes.new_from_object(ev)
    # (Grid to Mesh leaves a few zero-area faces where thin parts meet the grid — 18 on a dragon guard's wing tips,
    #  a failed degenerate_faces gate): dissolved, the surface otherwise unchanged
    import bmesh  # noqa: PLC0415

    bm = bmesh.new()
    bm.from_mesh(new)
    bmesh.ops.dissolve_degenerate(bm, dist=float(voxel) * 0.05, edges=bm.edges[:])
    # (dissolving leaves stray wire edges, loose vertices and small holes: removed and closed — watertight again)
    bmesh.ops.delete(bm, geom=[e for e in bm.edges if not e.link_faces], context="EDGES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_edges], context="VERTS")
    bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary], sides=0)   # (any size: 0)
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3])
    bm.to_mesh(new)
    bm.free()
    obj.modifiers.remove(mod)
    obj.data = new
    bpy.data.meshes.remove(me)
    bpy.data.node_groups.remove(ng)
    for o, _op in parts:
        o.hide_render = True
        o.hide_viewport = True
    return obj
