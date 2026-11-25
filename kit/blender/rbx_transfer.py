"""rbx_transfer.py — `kit optimize`: the GAME version's maps are a TRANSFER of the master's own baked maps.

The master (rbx.Asset(stage="master")) already baked its procedural material, masks, AO and wear into maps on its own
UVs. The game mesh (the master's join cut to the budget, rbx_optimize.reduce) gets those maps by a Cycles
selected-to-active bake from the master's saved objects (build/models/<master>.blend + its manifest's maps):
  color / rough / metal / emissive   EMIT of the master's map (on the master's UVs)
  normal                             NORMAL (tangent) of the master's surface WITH its own baked normal map connected
Nothing procedural is evaluated again on the game mesh (experiments/exp2-exp3: re-deriving the material at game
resolution darkened and blotched it; the transfer passed the albedo and normal fidelity on every test asset).
cage(...) = the ray cage: max(2 mm, 1.5 x the 99th percentile master->game deviation); rays reach 3 x the cage.
"""

import json
import os
import time

import bpy
from mathutils import Vector

CAGE_FLOOR_MM = 2.0
MM_PER_STUD = 280.0  # (1 stud = 280 mm: the kit's scale when an asset declares none)
REACH = 3.0


def cage(p99_studs, mm_per_stud=None):
    """the cage (studs) for a game mesh whose surface moved p99_studs (99th percentile) from the master's -> cage"""
    return max(CAGE_FLOOR_MM / (mm_per_stud or MM_PER_STUD), 1.5 * p99_studs)


def master_manifest(exports, master):
    with open(os.path.join(exports, f"{master}.manifest.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _box(o, pad=0.0):
    pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
    return ([min(p[i] for p in pts) - pad for i in range(3)], [max(p[i] for p in pts) + pad for i in range(3)])


def _overlap(a, b):
    return all(a[0][i] <= b[1][i] and b[0][i] <= a[1][i] for i in range(3))


def load_sources(exports, repo, master, low, reach, collection):
    """the master's group objects (from its saved .blend) whose box meets low's (padded by the reach), linked into
    collection -> [(object, group, manifest group entry)]"""
    man = master_manifest(exports, master)
    names = {(master if g == "main" else f"{master}_{g}"): g for g in man["groups"]}
    with bpy.data.libraries.load(os.path.join(exports, f"{master}.blend"), link=False) as (src, dst):
        want = [n for n in src.objects if n in names]
        dst.objects = list(want)
    box = _box(low, reach)
    out = []
    for name, o in zip(want, dst.objects, strict=True):
        if o is None:
            continue
        g = names[name]
        if o.type != "MESH" or not _overlap(box, _box(o)):
            bpy.data.objects.remove(o)
            continue
        collection.objects.link(o)
        o.hide_render = False
        out.append((o, g, man["groups"][g]))
    return out, man


def _image(repo, rel, data, cache):
    if rel not in cache:
        img = bpy.data.images.load(os.path.join(repo, rel), check_existing=False)
        img.colorspace_settings.name = "Non-Color" if data else "sRGB"
        # a master's colour map that cuts or fades it (a.cutout, a.fade) carries an alpha. Its COLOUR is taken as
        # it is in the file: read "associated", a half-clear texel comes out half as light - a faded pane's game
        # version was baked a dirty dark fade and failed game_fidelity (found by the fade's review)
        img.alpha_mode = "CHANNEL_PACKED"
        cache[rel] = img
    return cache[rel]


def _source_material(channel, entry, repo, cache):
    """ONE material for a master object in this pass: its own map of `channel` on its own UVs (the active-render
    layer, as its baked material sampled it)"""
    m = bpy.data.materials.new(f"transfer_{channel}")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    rel = entry["textures"].get(channel)
    tex = None
    if rel:
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = _image(repo, rel, channel != "color", cache)
    if channel == "normal":
        p = nt.nodes.new("ShaderNodeBsdfPrincipled")
        if tex is not None:
            nmap = nt.nodes.new("ShaderNodeNormalMap")
            nmap.space = "TANGENT"
            nt.links.new(tex.outputs["Color"], nmap.inputs["Color"])
            nt.links.new(nmap.outputs["Normal"], p.inputs["Normal"])
        nt.links.new(p.outputs["BSDF"], out.inputs["Surface"])
    else:
        em = nt.nodes.new("ShaderNodeEmission")
        if tex is not None:
            nt.links.new(tex.outputs["Color"], em.inputs["Color"])
        else:
            em.inputs["Color"].default_value = (0, 0, 0, 1)
        nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    return m


def bake(asset, obj, group, cage_studs, *, exports, textures, repo, rel, cycles_device):
    """obj (the game mesh, unwrapped) <- the master's maps -> (textures, alpha, strength), as rbx.Asset._bake_inner"""
    import numpy as np

    sc = asset.scene
    reach = cage_studs * REACH
    sources, _man = load_sources(exports, repo, asset.optimize_of, obj, reach, asset.collection)
    if not sources:
        raise RuntimeError(f"kit optimize: no part of the master {asset.optimize_of} lies within {reach:.4f} studs of "
                           f"{obj.name} — rebuild the master (lune run kit asset {asset.optimize_of}), then optimize")
    glow = max(float(e.get("emissiveStrength") or 0) for _o, _g, e in sources)
    alpha = min(1 - float(e.get("transparency") or 0) for _o, _g, e in sources)
    channels = ["color", "rough", "metal", "normal"] + (["emissive"] if glow > 0 else [])
    sc.render.engine = "CYCLES"
    cycles_device(sc)
    sc.render.bake.margin = 8
    sc.render.bake.use_clear = True
    sc.cycles.samples = 1
    orig = list(obj.data.materials)
    hidden = [o for o in sc.objects if o.type == "MESH" and not o.hide_render
              and o is not obj and all(o is not s for s, _g, _e in sources)]
    for o in hidden:
        o.hide_render = True
    images, made, cache, seconds = {}, [], {}, {}
    try:
        for ch in channels:
            for o, _g, e in sources:
                m = _source_material(ch, e, repo, cache)
                made.append(m)
                o.data.materials.clear()
                o.data.materials.append(m)
            img = bpy.data.images.new(f"{obj.name}_{ch}", asset.tex, asset.tex, alpha=False)
            if ch != "color":
                img.colorspace_settings.name = "Non-Color"
            target = bpy.data.materials.new(f"transfer_target_{ch}")
            target.use_nodes = True
            node = target.node_tree.nodes.new("ShaderNodeTexImage")
            node.image = img
            target.node_tree.nodes.active = node
            made.append(target)
            for i in range(len(obj.data.materials)):   # (every slot: the faces keep their material indices)
                obj.data.materials[i] = target
            if not obj.data.materials:
                obj.data.materials.append(target)
            bpy.ops.object.select_all(action="DESELECT")
            for o, _g, _e in sources:
                o.select_set(True)
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
            t0 = time.time()
            kind = dict(type="NORMAL", normal_space="TANGENT") if ch == "normal" else dict(type="EMIT")
            bpy.ops.object.bake(**kind, use_selected_to_active=True, cage_extrusion=cage_studs,
                                max_ray_distance=reach, margin=8)
            seconds[ch] = round(time.time() - t0, 2)
            img.filepath_raw = os.path.join(textures, f"{obj.name}_{ch}.png")
            img.file_format = "PNG"
            img.save()
            images[ch] = img
    finally:
        for o in hidden:
            o.hide_render = False
        obj.data.materials.clear()
        for m in orig:
            obj.data.materials.append(m)
        for o, _g, _e in sources:
            me = o.data
            bpy.data.objects.remove(o)
            if me.users == 0:
                bpy.data.meshes.remove(me)
        for m in made:
            if m.users == 0:
                bpy.data.materials.remove(m)
        for img in cache.values():
            bpy.data.images.remove(img)
    # (the roughness each material shows, measured on the transferred map over the faces it covers, as a bake does)
    rough = np.array(images["rough"].pixels[:], dtype=np.float32).reshape(asset.tex, asset.tex, 4)
    asset._rough_zones[obj.name] = asset._measure_rough(obj, rough[..., 0], {v["mat"].name: v for v in asset.mats.values()})
    asset._transfer_facts[group] = {"sources": sorted({g for _o, g, _e in sources}), "seconds": seconds,
                                    "cage_studs": round(cage_studs, 5), "reach_studs": round(reach, 5)}
    asset._apply_baked(obj, images, alpha, glow)
    return {ch: rel(images[ch].filepath_raw) for ch in images}, alpha, glow
