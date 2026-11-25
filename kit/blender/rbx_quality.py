"""rbx_quality.py — the quality BAR. A model that merely builds is not done; it is done when it is GOOD.

Every build is MEASURED here (in Blender) and scored by rbx_score (weights fitted to the owner's blind grades):
  silhouette   how much the outline breaks up (concavity vs its convex hull)
  detail       crease density on flat-lit cavity renders (panel lines, insets, bolts, fins, vents...)
  empty        share of the surface that is a blank expanse — no creases AND no visible texture (an albedo pass sees
               grain, stencils, wear); the owner's grades weigh it little
  variety      kinds of small detail parts for the tier (bolts, screws, latches, LEDs, markings...)
  geometry     triangles near the tier's budget (over 1.5x costs)
  materials    distinct material zones covering real area + value contrast between them
  surface      the surface story: rounded-edge normals, AO, edge wear, paint chipping / grime
  texture      the texture a player SEES: the albedo views' band-pass contrast (2..18 px at 1024 px — grain, wear,
               grime, chips, stencils; never the 1-px bake noise a player cannot resolve) on crease-free surface
  markings     text / serials / warning marks (hero + aaa tiers)
  reference    silhouette match against the owner's reference picture (when one is given)
  craft        plausibility, a FACTOR on the whole score: wood carved instead of built (4+ grooves / recesses or 8+
               cuts of any shape), see-through gaps in a wooden model (each scaled by how much is wrong) — named,
               with the fix, whenever it costs anything
Tiers (rbx.Asset(quality=...)): prop 55 — the calibrated score, on the OWNER's scale (kit/grades.json), decides;
hero 75 · aaa 88 — the raw measured score is only a FLOOR, and the verdict is an independent judge's (kit judge).
Below the bar the build FAILS, and next_action names the weakest component with WHERE on the model to work. An
accepted build (kit accept) is a floor: the ratchet fails a later build that scores worse. Each build is appended to
build/models/<name>.quality.json so iterations are visible.
"""

import json
import math
import os
import re
import time

import bpy
from mathutils import Vector

import rbx_image as I  # noqa: E402 — the image measurements (plain numpy, unit-tested)
from rbx_score import (  # noqa: F401 — TIERS / VARIETY_TARGET / TRI_TARGET / WEIGHTS / raw_of are read through here
    MEASURE_VERSION,
    RATCHET_RAW,
    TIERS,
    TRI_TARGET,
    VARIETY_TARGET,
    WEIGHTS,
    accepted,
    calibrate,
    fingerprint_diff,
    is_wood_name,
    iteration_of,
    effective,
    ratchet,
    raw_of,
)

RES = 1024


def _hull_area(points):
    """Monotone-chain convex hull area of 2D points."""
    pts = sorted(set(points))
    if len(pts) < 3:
        return 0.0

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    hull = lower[:-1] + upper[:-1]
    area = 0.0
    for i in range(len(hull)):
        x1, y1 = hull[i]
        x2, y2 = hull[(i + 1) % len(hull)]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2


def _detail_images(objs):  # noqa: C901
    """Give every baked material a temporary 'detail' texture: its NORMAL map lit by a raking light (in tangent
    space) times its colour's relative luminance. Baked plates, screws, vents and stencils (floaters) then show
    in the quality renders exactly like modelled ones — the score sees what the player sees, not just triangles.
    -> cleanup list [(node tree, node, previous active node, image)]"""
    import numpy as np

    light = np.array([0.55, 0.55, 0.62], dtype=np.float32)
    light /= np.linalg.norm(light)
    done, cleanup = set(), []
    for o in objs:
        for mat in getattr(o.data, "materials", []) or []:
            if mat is None or mat.name in done or not mat.use_nodes:
                continue
            done.add(mat.name)
            # the channel from the image's name — a cached build appends its .blend, so names can carry ".png" or a
            # ".001" suffix: an exact "_color" match missed them and the score went TEXTURE-BLIND (flat grey views)
            imgs = {}
            for n in mat.node_tree.nodes:
                if n.type == "TEX_IMAGE" and n.image:
                    hit = re.search(r"_(color|normal|rough|metal|emissive)(?:\.png)?(?:\.\d{3})?$", n.image.name)
                    if hit:
                        imgs[hit.group(1)] = n.image
            col, nrm = imgs.get("color"), imgs.get("normal")
            if col is None:
                continue
            w, h = col.size
            c = np.empty(w * h * 4, dtype=np.float32)
            col.pixels.foreach_get(c)
            c = c.reshape(h, w, 4)
            shade = np.ones((h, w), dtype=np.float32)
            if nrm is not None and tuple(nrm.size) == (w, h):
                n = np.empty(w * h * 4, dtype=np.float32)
                nrm.pixels.foreach_get(n)
                n = n.reshape(h, w, 4)[..., :3] * 2 - 1
                shade = np.clip(n @ light, 0, 1) / light[2]
            lum = c[..., 0] * 0.3 + c[..., 1] * 0.59 + c[..., 2] * 0.11
            ref = float(np.median(lum[lum > 0.001])) if (lum > 0.001).any() else 0.5
            rel = np.clip(lum / max(ref, 1e-3), 0, 2)
            v = np.clip(0.6 * shade * (0.6 + 0.4 * rel), 0, 1)
            out = np.dstack([v, v, v, np.ones_like(v)]).astype(np.float32)
            img = bpy.data.images.new(f"_q_detail_{mat.name}", w, h, alpha=False)
            img.colorspace_settings.name = "Non-Color"
            img.pixels.foreach_set(out.ravel())
            nt = mat.node_tree
            node = nt.nodes.new("ShaderNodeTexImage")
            node.image = img
            prev = nt.nodes.active
            nt.nodes.active = node
            cleanup.append((nt, node, prev, img))
    return cleanup


def _render_views(objs, out_dir, name):
    """Flat-lit + cavity orthographic renders: side (+X), top (+Y), front (-Z). Baked detail shows through the
    detail texture (see _detail_images); geometric creases through cavity. -> {view: (path, frame)}"""
    sc = bpy.context.scene
    detail = _detail_images(objs)
    keep = {o.name for o in objs}
    hidden = []
    for o in sc.objects:
        if o.type in ("MESH", "CURVE", "FONT") and o.name not in keep and not o.hide_render:
            o.hide_render = True
            hidden.append(o)
    corners = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    lo = Vector((min(c.x for c in corners), min(c.y for c in corners), min(c.z for c in corners)))
    hi = Vector((max(c.x for c in corners), max(c.y for c in corners), max(c.z for c in corners)))
    center = (lo + hi) / 2
    ex = hi - lo
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.render.film_transparent = True
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.view_settings.exposure = 0.0  # (a studio render before this must not leave its exposure)
    sh = sc.display.shading
    sh.light = "FLAT"
    sh.color_type = "TEXTURE" if detail else "SINGLE"
    sh.single_color = (0.6, 0.6, 0.6)
    sh.show_cavity = True
    sh.cavity_type = "BOTH"
    sh.cavity_ridge_factor = 2.0
    sh.cavity_valley_factor = 2.0
    sh.curvature_ridge_factor = 2.0
    sh.curvature_valley_factor = 2.0
    sh.show_object_outline = False
    cam = bpy.data.objects.new("QualityCam", bpy.data.cameras.new("QualityCam"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.data.type = "ORTHO"
    out = {}
    # each baked material's own COLOUR node: the albedo pass shows it (what the player sees), the detail pass does not
    colour = {}
    for nt, _node, _prev, _img in detail:
        for n in nt.nodes:
            if n.type == "TEX_IMAGE" and n.image and re.search(r"_color(?:\.png)?(?:\.\d{3})?$", n.image.name):
                colour[nt] = n
    # Blender axes: x = Roblox x, y = Roblox -z, z = Roblox y
    for view, direction, (w, h) in (
        ("side", Vector((1, 0, 0)), (ex.y, ex.z)),
        ("top", Vector((0, 0, 1)), (ex.x, ex.y)),
        ("front", Vector((0, 1, 0)), (ex.x, ex.z)),  # Blender +y = Roblox -z: the model's front
    ):
        span = max(w, h) * 1.08
        rx = RES
        ry = max(64, int(RES * h / max(w, 1e-6))) if w >= h else RES
        if w < h:
            rx = max(64, int(RES * w / max(h, 1e-6)))
        sc.render.resolution_x, sc.render.resolution_y = rx, ry
        cam.data.ortho_scale = span
        cam.location = center + direction * (max(ex) * 3 + 10)
        cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y" if view != "top" else "Y").to_euler()
        if view == "top":
            cam.rotation_euler = (0, 0, 0)
        cam.data.clip_end = max(ex) * 10 + 100
        path = os.path.join(out_dir, f"_q_{name}_{view}.png")
        sc.render.filepath = path
        bpy.ops.render.render(write_still=True)
        albedo = None
        if colour:
            # the ALBEDO pass: the same view in the plain baked colour, no cavity — grain, stencils and wear live here
            # (the detail image weighs colour at 0.24 to read SHAPE: grain survives there as a 1% ripple)
            for nt, node in colour.items():
                nt.nodes.active = node
            sh.show_cavity = False
            albedo = os.path.join(out_dir, f"_q_{name}_{view}_albedo.png")
            sc.render.filepath = albedo
            bpy.ops.render.render(write_still=True)
            sh.show_cavity = True
            for nt, node, _prev, _img in detail:
                nt.nodes.active = node
        out[view] = (path, {"span": span, "rx": rx, "ry": ry, "center": tuple(center), "maps": len(detail),
                            "albedo": albedo})
    bpy.data.objects.remove(cam)
    for o in hidden:
        o.hide_render = False
    for nt, node, prev, img in detail:
        nt.nodes.remove(node)
        if prev is not None:
            nt.nodes.active = prev
        bpy.data.images.remove(img)
    sh.color_type = "SINGLE"
    sc.render.film_transparent = False
    return out


TEX_SEEN = 0.004  # a block whose median albedo contrast (rbx_image.visible_texture) is above 0.4% carries visible
# texture. Measured: the selftest's flat-painted boards 0.24%, the same boards with grain 0.57% (grained crate 1.1%)
TEX_STD = 0.006  # (no baked maps: the detail image's own std decides, as before)
TEXTURE_FULL = 0.012  # median visible contrast for full texture credit (75th percentile of the owner-graded builds;
# the most textured ones — the sci-fi pistols, the Barretts — measure 2-3%). More earns nothing; it is not penalised
# either: the grades give no evidence for a ceiling yet (and the measure cannot tell meaningless noise from grain)
BUSY = 0.15  # a block with more than this share of crease pixels is BUSY (dense detail: no rest for the eye)
SEE_THROUGH = 0.003  # thin see-through gaps above 0.3% of the silhouette: slats / boards that do not meet
CARVED_SHARE = 0.08  # wood whose surface is 8%+ carved walls is carved, not built (a keyhole and two mortises: ~1%)


def _measure(path, albedo=None):
    """-> {concavity, edge (crease share), empty (texture-aware), busy (dense-crease share), blocks (biggest empty
    rectangles, px), shape}. EMPTY = no creases AND no visible texture: a grained board, a stencil or worn paint is
    surface the player reads, not a blank (the old crease-only test called every honest plank empty and its advice,
    "put grooves there", carved noise into the starters). BUSY = blocks thick with creases: craft leaves the eye calm
    areas between clusters of detail; noise covers everything at one density."""
    import numpy as np

    img = bpy.data.images.load(path)
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    px = px.reshape(h, w, 4)[::-1]  # top row first
    mask = px[..., 3] > 0.5
    area = int(mask.sum())
    if area < 50:
        return {"concavity": 0.0, "edge": 0.0, "empty": 1.0, "busy": 0.0, "see_through": 0.0, "blocks": None,
                "texture": 0.0, "textured_view": False, "texture_px": 0, "inside_px": 0, "shape": mask.shape}
    # silhouette: concavity against the convex hull (boundary points only, subsampled)
    ys, xs = np.nonzero(mask)
    step = max(1, len(xs) // 6000)
    hull = _hull_area(list(zip(xs[::step].tolist(), ys[::step].tolist())))
    concavity = max(0.0, 1 - area / hull) if hull > 0 else 0.0
    # creases: gradient of the flat-lit cavity render inside the eroded mask (the outline itself does not count)
    gray = px[..., 0] * 0.3 + px[..., 1] * 0.59 + px[..., 2] * 0.11
    edge, inner = I.creases(gray, mask)
    inside = max(1, int(inner.sum()))
    edge_frac = float(edge.sum()) / inside
    # VISIBLE TEXTURE: the albedo pass's band-pass contrast on crease-free surface (rbx_image.visible_texture: grain,
    # wear, grime, chips, stencils — relative to the local brightness, so dark wood counts like light wood)
    seen, seen_ok, texture = None, None, 0.0
    if albedo and os.path.isfile(albedo):
        ai = bpy.data.images.load(albedo)
        ap = np.empty(ai.size[0] * ai.size[1] * 4, dtype=np.float32)
        ai.pixels.foreach_get(ap)
        bpy.data.images.remove(ai)
        ap = ap.reshape(h, w, 4)[::-1]  # (same size as the view: rendered at the same resolution)
        lum = ap[..., 0] * 0.3 + ap[..., 1] * 0.59 + ap[..., 2] * 0.11
        seen, seen_ok = I.visible_texture(lum, inner, edge)
        texture = float(np.median(seen[seen_ok])) if seen_ok.any() else 0.0
    # 24 px blocks fully inside: EMPTY = no creases and no visible texture; BUSY = thick with creases
    b = 24
    empty, busy, total, best = 0, 0, 0, None
    rows, cols = mask.shape[0] // b, mask.shape[1] // b
    grid = np.zeros((rows, cols), dtype=bool)
    for r in range(rows):
        for c in range(cols):
            sl = (slice(r * b, (r + 1) * b), slice(c * b, (c + 1) * b))
            if inner[sl].all():
                total += 1
                creases = edge[sl].mean()
                if creases > BUSY:
                    busy += 1
                elif creases < 0.004:
                    if seen is not None:
                        ok = seen_ok[sl]
                        textured = int(ok.sum()) >= 50 and float(np.median(seen[sl][ok])) >= TEX_SEEN
                    else:
                        textured = gray[sl].std() >= TEX_STD
                    if not textured:
                        empty += 1
                        grid[r, c] = True
    # the three biggest empty rectangles (greedy: take the largest, clear it, repeat) — places to work on
    blocks = []
    work = grid.copy()
    for _ in range(3):
        best_area, best = 0, None
        for r in range(rows):
            c = 0
            while c < cols:
                if work[r, c]:
                    c0 = c
                    while c < cols and work[r, c]:
                        c += 1
                    rr = r
                    while rr + 1 < rows and work[rr + 1, c0:c].all():
                        rr += 1
                    a = (c - c0) * (rr - r + 1)
                    if a > best_area:
                        best_area, best = a, (c0, r, c - c0, rr - r + 1)
                else:
                    c += 1
        if not best:
            break
        c0, r0, wc, hr = best
        work[r0:r0 + hr, c0:c0 + wc] = False
        blocks.append((c0 * b, r0 * b, wc * b, hr * b))
    return {"concavity": concavity, "edge": edge_frac, "empty": empty / total if total else 0.0,
            "busy": busy / total if total else 0.0, "see_through": I.see_through(mask), "blocks": blocks,
            "texture": texture, "textured_view": seen is not None,
            "texture_px": int(seen_ok.sum()) if seen_ok is not None else 0, "inside_px": inside, "shape": mask.shape}


def _where(view, frame, block):
    """pixel block on a view -> a Roblox-space description"""
    if not block:
        return ""
    x, y, w, h = block
    span, rx, ry, c = frame["span"], frame["rx"], frame["ry"], frame["center"]
    ppu = rx / span if rx >= ry else ry / span
    cx_px, cy_px = x + w / 2, y + h / 2
    du, dv = (cx_px - rx / 2) / ppu, -(cy_px - ry / 2) / ppu
    ws, hs = w / ppu, h / ppu
    if view == "side":  # camera at +X looking -X: screen right = Blender +y = Roblox -z (the model's front)
        return f"the side around z={-(c[1] + du):.2f} (front is -z), y={c[2] + dv:.2f} — a flat {ws:.1f} x {hs:.1f} stud expanse"
    if view == "top":
        return f"the top around x={c[0] + du:.2f}, z={-(c[1] + dv):.2f} — a flat {ws:.1f} x {hs:.1f} stud expanse"
    # front view: camera at Blender +y looking -y: screen right = Blender -x
    return f"the front around x={c[0] - du:.2f}, y={c[2] + dv:.2f} — a flat {ws:.1f} x {hs:.1f} stud expanse"


def score(asset, objs, part_stats, renders_dir, reference_iou=None):
    """-> (report dict, design checks list). asset: rbx.Asset; part_stats: from collect()."""
    master = getattr(asset, "stage", "game") == "master"
    tier = asset.quality
    views = _render_views(objs, renders_dir, asset.name)
    m = {}
    for view, (path, frame) in views.items():
        r = _measure(path, frame.get("albedo"))
        m[view] = {"concavity": r["concavity"], "detail": r["edge"], "empty": r["empty"], "busy": r["busy"],
                   "see_through": r["see_through"], "texture": r["texture"], "textured_view": r["textured_view"],
                   "texture_px": r["texture_px"], "inside_px": r["inside_px"],
                   "block": r["blocks"], "frame": frame}  # block = list
        if not os.environ.get("KIT_BAKE_DEBUG"):  # debug keeps the views the score measured
            for p_ in (path, frame.get("albedo")):
                if p_ and os.path.isfile(p_):
                    os.remove(p_)
    # side view matters most for long props (weapons, vehicles); average for the rest
    wts = {"side": 0.5, "top": 0.25, "front": 0.25}
    conc = sum(m[v]["concavity"] * wts[v] for v in m)
    detail = sum(m[v]["detail"] * wts[v] for v in m)
    empty = sum(m[v]["empty"] * wts[v] for v in m)
    busy = sum(m[v]["busy"] * wts[v] for v in m)
    see_through = max(m[v]["see_through"] for v in m)  # the worst view: one see-through face is enough
    # CRAFT (plausibility) scales the whole score. What the geometry CAN judge it charges, scaled by HOW MUCH is wrong:
    # - wood CARVED instead of built, on a model at least a quarter wood: 4+ groove / recess-shaped cuts (the
    #   score-chasing crate's 40 carved grooves cost ~60%), or 8+ cuts into wood of any shape (notches in a row are
    #   carving too); a door's keyhole, hinge mortises and handle slots — a few chunky cuts — are joinery and never cost
    # - see-through slits in a model that is mostly WOOD (no real chest or crate lets light through its lid) — unless
    #   the asset declares a see-through design (Asset(see_through=True): rails, grilles, slats meant to be open)
    # What it cannot judge it only NAMES (warnings): cuts through a part (the M107's scope rings are split on purpose;
    # a cut(..., through=True) says so), slits in a non-wood model (a railgun's twin rails are design — measured: the
    # owner's 80-graded railgun shows MORE slit than the agent chest).
    # the WOOD's surface = its own faces + the walls carved into it (a groove's walls take the cutter's material, but they
    # are the wood's own carved surface: counting them out let a model carve itself below the "wooden" line — the
    # score-chased crate's 289 dark grooves left 24% of its surface wood, the gate's line is 25%)
    carved_area = part_stats.get("carved_area", 0.0)  # every wall carved into wood that is still there (collect)
    wood_surface = part_stats.get("wood_area", 0.0) + part_stats.get("carved_other_area", 0.0)
    seen = part_stats.get("seen_area", 0.0)
    wood_share = min(1.0, wood_surface / seen) if seen > 0 else part_stats.get("wood_share", 0.0)
    grooves = asset.design.get("wood_grooves") or []
    wood_cuts = asset.design.get("wood_cuts") or []
    # counted in CARVED REGIONS (each groove / notch / recess the cuts left), not in cut() calls: one comb-shaped
    # cutter carving 37 grooves is 37 grooves (rbx.cut counts the regions of the cutter's material it leaves)
    # ... and the lines BAKED onto wood (floaters: a seam drawn in the maps is a groove to the eye)
    n_lines = part_stats.get("wood_lines", 0)
    n_grooves = asset.design.get("wood_groove_regions", len(grooves)) + n_lines
    n_regions = asset.design.get("wood_cut_regions", len(wood_cuts)) + n_lines
    # ... and in AREA: one connected carving (a comb whose spine scrapes the surface) is one region, not one groove
    carved_share = carved_area / wood_surface if wood_surface > 0 else 0.0
    carving = wood_share >= 0.25 and (n_grooves >= 4 or n_regions >= 8 or carved_share >= CARVED_SHARE)
    n_carved = max(n_grooves, n_regions) if carving else 0
    open_ok = bool(asset.design.get("see_through_ok"))
    wooden_gaps = see_through > SEE_THROUGH and wood_share >= 0.5 and not open_ok
    lines_said = (f"; {n_lines} of them lines baked on the wood ({', '.join(part_stats.get('wood_line_names') or [])})"
                  if n_lines else "")
    defects = ([f"{n_regions} regions carved into wood ({carved_share:.0%} of its surface), {n_grooves} of them grooves / recesses "
                f"({', '.join((grooves or wood_cuts or part_stats.get('wood_line_names') or [])[:2])}...){lines_said}"]
               if carving else []) + (
        [f"see-through gaps in a wooden model ({see_through:.2%} of the silhouette)"] if wooden_gaps else [])
    # every empty region on every view, biggest (in studs²) first
    regions = []
    for v in m:
        fr = m[v]["frame"]
        ppu = (fr["rx"] if fr["rx"] >= fr["ry"] else fr["ry"]) / fr["span"]
        for blk in m[v]["block"] or []:
            regions.append(((blk[2] / ppu) * (blk[3] / ppu), _where(v, fr, blk)))
    regions.sort(key=lambda r: -r[0])
    where = "; ".join(r[1] for r in regions[:3]) or "nowhere big"

    # visible texture: the albedo views' median contrast, weighted like the other view measures — over the views where
    # the surface can be measured at all (a blade or a rod seen edge-on is a strip too thin for the 2-18 px bands:
    # counting it as "no texture" capped every slender prop at half credit). No baked maps -> 0.
    tex_views = [v for v in m if m[v]["textured_view"] and m[v]["texture_px"] >= max(400, 0.05 * m[v]["inside_px"])]
    if not tex_views:  # (a staff or a spear: every view a thin strip — the view with the most surface still speaks)
        fallback = max((v for v in m if m[v]["textured_view"] and m[v]["texture_px"] >= 50),
                       key=lambda v: m[v]["texture_px"], default=None)
        tex_views = [fallback] if fallback else []
    texture = (sum(m[v]["texture"] * wts[v] for v in tex_views) / sum(wts[v] for v in tex_views)) if tex_views else 0.0
    tris = sum(len(p.vertices) - 2 for o in objs for p in o.data.polygons) - part_stats.get("internal_tris", 0)
    comp = {
        "silhouette": min(1.0, conc / 0.2),
        "detail": min(1.0, detail / 0.4),
        "empty": max(0.0, 1 - empty / 0.25),
        "variety": min(1.0, part_stats["kinds"] / VARIETY_TARGET[tier]),
        # enough triangles to carry the forms — but over 1.5x the budget is waste (Roblox: 20k per mesh). A MASTER
        # (Asset(stage="master")) has no budget: it is the no-limits original `kit optimize` makes the game mesh from
        # (it still needs enough triangles to carry its forms: only the over-budget charge is lifted)
        "geometry": min(1.0, tris / TRI_TARGET[tier]) if (master or tris <= TRI_TARGET[tier] * 1.5)
        else max(0.0, 1 - (tris - TRI_TARGET[tier] * 1.5) / TRI_TARGET[tier]),
        "materials": min(1.0, part_stats["zones"] / 4) * 0.6 + min(1.0, part_stats["contrast"] / 0.25) * 0.4,
        "surface": part_stats["surface"],
        "texture": min(1.0, texture / TEXTURE_FULL),
        "markings": 1.0 if part_stats["markings"] else 0.0,
        "craft": 1.0,  # (set below: the craft factor that scales the score)
    }
    # ORGANIC: the share of what is seen that was sculpted (a.sculpt) — plus its imported meshes when the asset declares
    # form="organic" (a generated creature, a scanned rock); form="hard": none. Unweighted itself: it lets surface detail
    # earn variety and colour variation earn materials (rbx_score.effective), as an organic form's would
    form = asset.design.get("form")   # (declared organic counts the IMPORTED meshes too — never the kit's own parts)
    organic = 0.0 if form == "hard" else float(part_stats.get("organic", 0.0)) + (
        float(part_stats.get("imported", 0.0)) if form == "organic" else 0.0)
    if organic > 0:
        comp["organic"] = round(organic, 3)
    weights = dict(WEIGHTS)
    if tier == "prop":
        weights["markings"] = 0
    if reference_iou is None:
        weights["reference"] = 0
    else:
        comp["reference"] = min(1.0, reference_iou / 0.85)
    # a model made the way the real object never is must not keep the detail credit its carving bought (selftest:
    # a groove-carved block never outscores real boards). Capped at 75%.
    severity = (max(0.1 + 0.012 * n_carved, 0.1 + carved_share) if carving else 0.0) + (
        (0.1 + 5 * see_through) if wooden_gaps else 0.0)
    craft_factor = 1.0 - min(0.75, severity)
    comp["craft"] = craft_factor  # (reported; it scales the score below rather than adding a weighted share)
    raw = raw_of(comp, tier)
    # the OWNER's eye sets the scale (kit grade): raw measurements are mapped through every owner grade
    estimate, grades_used = calibrate(raw)
    bar = TIERS[tier]
    # hero / aaa: the measured score is a FLOOR (coverage, budget, variety, surface) — the quality verdict comes from
    # an independent judge (`kit judge`), never from the builder's own numbers. prop: the calibrated score decides.
    judged = tier in ("hero", "aaa")
    value = raw if judged else estimate
    fixes = {
        "silhouette": "the outline is too boxy — break it: chamfer/angle the ends, step the top line, cut notches, add protruding forms (mounts, guards, fins) so the side view is not a rectangle",
        "detail": ("surfaces are too plain — add the secondary forms the REAL object has: on hard-surface parts inset "
                   "panels (P.inset_panel), raised plates (P.plate), panel lines, vents, fins; on wood separate boards, "
                   "battens and metal hardware (brackets, hinges, nails, bolts) — never grooves carved into planks"
                   if wood_share < 0.5 else
                   "surfaces are too plain — a wooden model's detail is real construction: separate boards (gaps over a "
                   "dark core), battens, braces, metal hardware (brackets, hinges, nails, bolts, handles on mounts), "
                   "stencils — never grooves carved into planks"),
        "empty": f"featureless expanses (biggest first): {where} — blank to the eye: give the surface what the REAL "
                 "object has there — a texture (material pattern=, wear=, grime=; wood: pattern=\"wood\" and separate "
                 "boards), its real hardware (plates, fasteners, hinges, labels, markings) — never grooves or clutter "
                 "carved in just to fill it",
        "variety": f"only {part_stats['kinds']} kinds of small detail (a {tier} needs {VARIETY_TARGET[tier]}+ different kinds; copies do not count) — screws, latches, LEDs, connectors, knurled rings, cables, vents, labels (rbx_parts)",
        "geometry": (
            f"{tris} triangles — a master is not budgeted: kit optimize <asset> makes the game mesh from it"
            if master
            else f"{tris} triangles — a {tier} carries ~{TRI_TARGET[tier]}: spend them on bevels, curved forms, recesses and secondary shapes, not flat boxes"
            if tris <= TRI_TARGET[tier] * 1.5
            else f"{tris} triangles is over budget ({TRI_TARGET[tier]} for {tier}; Roblox caps a mesh at 20000) — biggest costs: "
            + ", ".join(f"{k} {v}" for k, v in part_stats["costs"])
            + " — lower segments, merge repeated details, or move small detail to its own group="
        ),
        "texture": f"the surface reads as flat colour (visible texture {texture:.2%} median contrast, want {TEXTURE_FULL:.1%}) "
                   "— give each material what the real one has: wood pattern=\"wood\", worn paint wear= + chip=, grime= "
                   "in crevices, stencils and labels; flat colour reads as plastic (more than this earns nothing: heavy "
                   "wear everywhere reads as noise to the owner)",
        "materials": f"{part_stats['zones']} material zone(s), contrast {part_stats['contrast']:.2f} — use 3-5 zones (frame, panels, rubber, metal, accent) with clear value steps",
        "surface": "surface story missing — material(... wear=0.3, chip=0.4, under=bare metal) for paint chipping, grime=0.4 for dirt in crevices",
        "markings": "no markings — a.text(...) serials / maker text, P.stripes warning bands, small labels (hero props carry identity)",
        "reference": "silhouette does not match the reference — fix proportions against build/renders/<name>_ref_<view>.png first",
        "craft": f"plausibility defects: {'; '.join(defects)} — close gaps you can see through, cut INTO parts not "
                 "through them, and give wood separate boards instead of carved grooves",
    }
    eff = effective(comp)   # (an organic model's variety / materials as the score weighs them)
    if comp.get("organic", 0) >= 0.5:   # (what an organic form is short of, said in its own terms)
        fixes["variety"] = (f"little surface detail for an organic form (crease density {detail:.2f}) — sculpt what the "
                            "real one has: ridges and fissures (noise kind ridged / cracks), creases, strokes for "
                            "folds and roots, small growths and debris (fungi, moss, pebbles) — not bolted-on hardware")
        fixes["materials"] = (f"one flat tone (visible texture {texture:.2%}) — give the organic surface its real "
                              "variation: a scan look (kit materials --looks: bark, mossy_bark, rock, rust...), vary=, "
                              "a life=, a second material where the real one changes (end grain, moss, wet soil)")
    ranked = sorted((k for k in eff if weights.get(k)), key=lambda k: (eff[k] - 1) * weights[k])
    if craft_factor < 1.0:  # a plausibility defect costs the WHOLE score: it is named first, with its fix
        ranked = ["craft"] + ranked
    weakest = ranked[0]
    report = {
        "tier": tier,
        "measure": MEASURE_VERSION,
        "bar": bar,
        "score": value,
        "raw": raw,
        "owner_estimate": estimate,
        "calibrated_by": f"{grades_used} owner grade(s)" if grades_used else "no owner grades yet (raw = score)",
        "final": "the judge decides: lune run kit judge " + asset.name if judged else "this score",
        "pass": value >= bar,
        "components": {k: round(v, 2) for k, v in comp.items()},
        "measures": {
            "concavity": round(conc, 3),
            "crease_density": round(detail, 3),
            "empty_share": round(empty, 3),
            "busy_share": round(busy, 3),
            "see_through": round(see_through, 4),
            "maps_seen": max((fr["maps"] for _p, fr in views.values()), default=0),
            "detail_kinds": part_stats["kinds"],
            "triangles": tris,
            "visible_texture": round(texture, 4),
            "texture_views": tex_views,
            "material_zones": part_stats["zones"],
            "triangle_costs": part_stats["costs"],
            # what craft judged: how much of the seen model is wood, how much of that wood is carved walls, the lines
            # baked on it, and the carved regions / grooves counted
            "wood_share": round(wood_share, 3),
            "carved_share": round(carved_share, 3),
            "craft": round(craft_factor, 3),
            "wood_lines": n_lines,
            "carved_regions": n_regions,
            "carved_grooves": n_grooves,
        },
        "weakest": weakest,
        "fix": fixes[weakest],
        "next": [fixes[k] for k in ranked[1:3] if eff[k] < 0.85],
    }
    # history: is each iteration better?
    hist_path = os.path.join(os.path.dirname(renders_dir), "models", f"{asset.name}.quality.json")
    try:
        with open(hist_path, encoding="utf-8") as fh:
            hist = json.load(fh)
    except (OSError, ValueError):
        hist = []
    # a rebuild of the same build is the same iteration, measured again (rbx_score.iteration_of)
    iteration, hist = iteration_of(hist, getattr(asset, "script_sha", None))
    prev = hist[-1]["score"] if hist else None
    # the build's FINGERPRINT travels with every grade of it: a re-measure that finds a different model (the kit's
    # geometry changed under the script) leaves the owner's grade alone instead of pinning it on what they never saw
    boxes = [_world_box(o) for o in objs]
    size = [round(max(b[1][i] for b in boxes) - min(b[0][i] for b in boxes), 3) for i in range(3)] if boxes else None
    hist.append({"at": time.strftime("%Y-%m-%d %H:%M:%S"), "iteration": iteration, "score": value, "raw": raw,
                 "components": report["components"], "measure": MEASURE_VERSION, "tier": tier,
                 "tris": int(tris), "size": size, "script_sha": getattr(asset, "script_sha", None)})
    with open(hist_path, "w", encoding="utf-8") as fh:
        json.dump(hist[-50:], fh, indent=1)
    report["previous"] = prev
    report["iteration"] = iteration
    from rbx_critic import _check

    delta = "" if prev is None else f" ({value - prev:+.1f} vs the previous iteration)"
    acc = accepted(asset.name)
    checks = []
    if acc is not None:  # ({} or a record without measurements is a floor too: a broken one, and it fails below)
        # the RATCHET: an accepted build is the floor for every later one (score-chasing drifted 33 -> 58 while the
        # model got uglier). Compared on TODAY's raw scale — the accepted build's own components re-scored now — so a
        # new owner grade or a refit of the weights can never fail a build that did not change.
        worse, then, how = ratchet(acc, raw, tier, measure=MEASURE_VERSION, now_comp=comp)
        if acc.get("from_git"):  # the file differs from the committed floor (or is gone): the committed one holds
            checks.append(_check(
                "floor_file", False, f"{acc['from_git']} differs from the committed floor (edited, broken or gone) — "
                "the committed floor holds", "the file is the committed floor",
                f"a change made by `kit accept` (a raise, a re-base, the OWNER's --lower) takes effect once committed: "
                f"commit {acc['from_git']}; any other change: restore the committed floor "
                f"({acc.get('restore') or 'git checkout HEAD -- ' + acc['from_git']})", "warn"))
        if how == "measure":
            # not comparable — so the floor can only vouch for its OWN build: this build passes only when its script
            # (the sha written when it was built) is the one that was accepted AND it is the floor's model (the
            # fingerprint the floor kept: a helper module or the kit can change the model under the same script); a
            # floor without a fingerprint vouches for nothing — the owner re-bases it
            own = (bool(getattr(asset, "script_sha", None)) and acc.get("script_sha") == asset.script_sha
                   and acc.get("tris") is not None and not fingerprint_diff(acc, {"tris": int(tris), "size": size}))
            if not own:
                report["pass"] = False
            checks.append(_check(
                "ratchet", own, f"the accepted build was measured by other measuring code (measure "
                f"{acc.get('measure', 'unversioned')}, now {MEASURE_VERSION})"
                + ("; this build is the accepted one (its script and model)" if own else
                   "; this build is NOT provably the accepted one (" + (
                       "another script" if acc.get("script_sha") != getattr(asset, "script_sha", None) else
                       "the floor kept no fingerprint" if acc.get("tris") is None else "another model")
                   + "): nothing vouches that it is not worse"),
                "an accepted build measured like this one, or this build the accepted one (script and model)",
                ("re-base the floor: `lune run kit accept " + asset.name + "` (the same script and model under new "
                 "measuring code)") if own else (
                    ("the floor predates fingerprints, so it cannot vouch for any build: the OWNER re-bases it (`lune "
                     "run kit accept " + asset.name + " \"their words\" --lower` at their terminal)")
                    if acc.get("script_sha") == getattr(asset, "script_sha", None) and acc.get("tris") is None else
                    ("the OWNER re-bases the floor (`lune run kit accept " + asset.name + " \"their words\" --lower` "
                     "at their terminal), or go back to the accepted build — never accept a different build just to "
                     "clear this")),
                "warn"))   # (report-only: the score never blocks a build — the owner and the judges decide)
        elif how is None:
            # a floor that cannot be read (broken and never committed, or with no measurements) FAILS the build: breaking
            # the record is never a way past the ratchet
            report["pass"] = False
            checks.append(_check(
                "ratchet", False, "the accepted record is unreadable or carries no measurements to compare against",
                "an accepted record with components", "restore the record (git checkout), or the OWNER re-makes the "
                "floor: rebuild the build they approved and `lune run kit accept " + asset.name + " \"the owner's "
                "words\" --lower` (confirmed at their terminal)", "warn"))
        else:
            report["ratchet"] = {"accepted_raw": then, "raw": raw, "iteration": acc.get("iteration"), "worse": worse,
                                 "compared": how}
            if worse:
                report["pass"] = False
            checks.append(_check(
                "ratchet", not worse, f"raw {raw} vs the accepted build's {then} (iteration {acc.get('iteration')}"
                + ("" if how == "components" else "; an old record: its raw may be on an older scale") + ")",
                f">= accepted - {RATCHET_RAW} raw",
                f"this build measures {then - raw:.1f} below the ACCEPTED build (iteration {acc.get('iteration')}) — undo "
                "the change that made it worse (look at what you added: clutter, grooves, flat colour), or if it really "
                "looks better, show the owner and re-accept: lune run kit accept " + asset.name,
                "warn"))
    declared = (["see_through=True (gaps are not judged)"] if open_ok else []) + [
        f"through=True on {c} (the split is not judged)" for c in (asset.design.get("through_cuts") or [])] + (
        ["stage_gate=False (detail is judged before the silhouette is right)"]
        if asset.design.get("stage_gate") is False and tier in ("hero", "aaa") else [])
    if declared:  # an opt-out silences a judgement: the verdict says so, so the owner sees what was declared
        checks.append(_check("declared", False, declared[:6], "nothing declared",
                             "these judgements are switched off by the build script — make sure each one is the design",
                             "warn"))
    checks += [
        _check(
            "see_through",
            see_through <= SEE_THROUGH or open_ok,
            f"{see_through:.2%} of the silhouette is thin gaps you can see through",
            f"<= {SEE_THROUGH:.1%}",
            "light passes between parts that should meet (slats with gaps, boards that do not close up) — put a core "
            "behind them (a dark box under the boards) or close the gaps; a real opening is wide, not a slit",
            "warn",
        ),
        _check(
            "quality",
            value >= bar,
            (f"floor {value}/100 (owner-scale estimate {estimate}){delta} — NOT the quality verdict: kit judge {asset.name}"
             if judged else f"{value}/100 (raw {raw}){delta}"),
            f"{tier} {'floor' if judged else 'bar'} {bar}",
            # (the score is a REPORT, never the target — its component advice once read "add 4+ kinds of small detail"
            #  and builders carved and greebled toward a number the owner rated 0.1/10: never add what the real object
            #  lacks; the weakest component is a pointer for the eye, said as one)
            f"a report, not a target ({value} < {bar}, weakest component: {weakest}) — LOOK at the render beside the "
            f"references and ask the verifier: lune run kit judge {asset.name}; change only what the REAL object has "
            "that this one lacks — never add parts, grooves or detail to move this number",
            "warn",   # (report-only, as the ratchet: a number is never the verdict — kit judge / the owner are)
        )
    ]
    # hero / aaa: a number is not enough — a fresh, written critique against the picture, every iteration
    if tier in ("hero", "aaa") and iteration > 1 and not getattr(asset, "optimize_of", None):  # (a game version's
        # critique is its master's: kit optimize measures what the cut lost instead)
        ok, why = _review_ok(asset.name, iteration - 1)
        report["review"] = why
        compare = f"build/renders/{asset.name}_compare.png" if asset.ref_image else f"build/renders/{asset.name}.png"
        checks.append(
            _check(
                "review",
                ok,
                why,
                f"assets/models/{asset.name}.review.md for iteration {iteration - 1}",
                f"write assets/models/{asset.name}.review.md: a line 'iteration: {iteration - 1}' (= the build you just "
                "looked at: its summary printed that number) and 5+ bullets — look at "
                f"{compare} (the whole) AND build/renders/{asset.name}_details.png (close-ups: every mount, joint, "
                "screw, gap, letter): what is STILL worse than the reference / an AAA game asset (shape, detail, surface, "
                "proportion, markings, anything floating or clipping), and what you change next. Rewrite it every "
                "iteration; never call it done early."
                + (f" This asset has a region map: run `lune run kit judge {asset.name}`, look at "
                   f"build/judge/{asset.name}/regions.png and write one '- <region>: ...' line per region."
                   if getattr(asset, "_region_boxes", None) else ""),
            )
        )
    # every model: the owner was ASKED what it is for (end goal, quality, function, extras, references, ownership) —
    # doing too much or too little both waste their time. Last of the checks: never hides a sharper next step
    ok, why = _brief_ok(asset)
    report["brief"] = why
    checks.append(
        _check(
            "brief",
            ok,
            why,
            f"assets/models/{asset.name}.brief.md answered",
            f"ask the owner the questions in assets/models/{asset.name}.brief.md (end goal, quality and its bar, "
            "style, how players see it, the hero features and how each gets made, moving parts, extras, references, "
            "ownership) and write their answers over each <answer> — `kit new asset` writes it; for an older model "
            "copy kit/templates/asset.brief.md beside its build script",
            "warn",
        )
    )
    return report, checks


def _brief_ok(asset):
    """The owner was asked: <name>.brief.md beside the build script, every <answer> written over."""
    import rbx_plan  # noqa: PLC0415

    # (a game version's brief is its master's)
    path = rbx_plan.brief_path(getattr(asset, "optimize_of", None) or asset.name, getattr(asset, "script_path", None))
    if not os.path.isfile(path):
        return False, "no brief: the owner was never asked what it is for"
    with open(path, encoding="utf-8") as fh:
        left = rbx_plan.unanswered_count(fh.read())  # (the template's intro naming `<answer>` is no question)
    if left:
        return False, f"{left} brief question(s) unanswered"
    return True, "the owner's answers are on file"


def _previous_build_id(name, models_folder):
    """the build the critique was about: the manifest on disk still holds the LAST build's id while this one runs"""
    builds = [os.environ["KIT_BUILD"]] if os.environ.get("KIT_BUILD") else []
    builds += [os.path.join(os.path.dirname(os.path.dirname(models_folder)), "build"), os.path.join(os.getcwd(), "build")]
    for build in builds:
        try:
            with open(os.path.join(build, "models", f"{name}.manifest.json"), encoding="utf-8") as fh:
                return json.load(fh).get("build_id")
        except (OSError, ValueError):
            continue
    return None


def _review_ok(name, iteration):
    """The critique file exists, is about the build just seen (iteration N-1) and lists 5+ concrete points."""
    import re
    import sys

    script = next((a for a in sys.argv if a.endswith(".py") and f"build_{name}" in a), None)
    folder = os.path.dirname(os.path.abspath(script)) if script else os.path.join(os.getcwd(), "assets", "models")
    # THE VERIFIER's round on the build just seen IS that critique, by a fresh reviewer instead of the builder: the
    # same crop of reference and render per view, a difference per image, one edit (kit judge, mission 01-3d 5.10)
    seen = _previous_build_id(name, folder)
    try:
        with open(os.path.join(folder, f"{name}.verify.json"), encoding="utf-8") as fh:
            rounds = json.load(fh).get("rounds") or []
    except (OSError, ValueError):
        rounds = []
    mine = [r for r in rounds if isinstance(r, dict) and seen and r.get("build") == seen]
    if mine:
        return True, f"the verifier's round {mine[-1].get('round')} on the build just seen ({seen})"
    path = os.path.join(folder, f"{name}.review.md")
    if not os.path.isfile(path):
        return False, "no review file (or: a verifier round on the build just seen — lune run kit judge " + name + ")"
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    m = re.search(r"iteration:\s*(\d+)", text)
    if not m or int(m.group(1)) != iteration:
        return False, f"review is for iteration {m.group(1) if m else '?'}, not {iteration}"
    bullets = [ln for ln in text.splitlines() if re.match(r"\s*[-*]\s+\S", ln)]
    if len(bullets) < 5:
        return False, f"only {len(bullets)} critique point(s)"
    # with a region map the critique must go region by region: one line per region, written from the region
    # sheet (reference crop beside the model close-up) — forced to LOOK at every part, not the whole at a glance
    regions_path = os.path.join(os.path.dirname(folder), "..", "refs", f"{name}.regions.json")
    if not os.path.isfile(regions_path):
        regions_path = os.path.join(os.getcwd(), "refs", f"{name}.regions.json")
    if os.path.isfile(regions_path):
        try:
            with open(regions_path, encoding="utf-8") as fh:
                names = [r["name"] for r in json.load(fh).get("regions", [])]
        except (OSError, ValueError, KeyError):
            names = []
        lines = [ln.strip().lower() for ln in text.splitlines()]
        missing = [n for n in names if not any(ln.lstrip("-* ").startswith(n.lower() + ":") for ln in lines)]
        if missing:
            return False, (f"no region line for: {', '.join(missing)} — write one '- <region>: what the reference has there "
                           "that the model lacks' line per region, from build/judge/<name>/regions.png (kit judge <name>)")
    return True, f"iteration {iteration}: {len(bullets)} points"


MARKING_WORDS = ("text", "decal", "mark", "code", "stripe", "label", "serial", "plate")


def _world_box(obj):
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    return (tuple(min(c[i] for c in corners) for i in range(3)), tuple(max(c[i] for c in corners) for i in range(3)))


def _wood_names(mats):
    """the materials that are WOOD: pattern="wood", or called so (rbx_score.is_wood_name)"""
    return {v["mat"].name for k, v in mats.items() if v.get("pattern") == "wood" or is_wood_name(k)}


def wood_lines(parts, mats, floaters, internal=(), float_depth=0.08):
    """LINES BAKED ON WOOD -> their names (one per floater): a thin non-metal floater lying on a seen wood part (a
    "seam", a fake board edge, a baked batten) draws into the maps what a carved groove cuts, so it counts with the
    grooves. Metal hardware (nails, bands, straps, brackets) and text (a.text, its mirrored copies too: tagged
    kit_marking — a stencil) are not lines of the wood; a NAME exempts nothing (a seam called "Plate" is a seam). Thin strips modelled as real parts are not
    looked at: they are geometry the silhouette and the triangle budget already pay for."""
    wood = _wood_names(mats)
    boxes = [_world_box(o) for o, _g in parts if o.name.split("~")[0] not in internal
             and any(m_ is not None and m_.name in wood for m_ in o.data.materials)]
    metal = {v["mat"].name for v in mats.values() if float(v.get("metal", 0.0)) >= 0.5}
    out = []
    for obj, _g in floaters if boxes else ():
        m0 = obj.data.materials[0] if obj.data.materials else None
        if obj.get("kit_text") is not None or obj.get("kit_marking") or (m0 is not None and m0.name in metal):
            continue
        lo, hi = _world_box(obj)
        thin, mid, long_ = sorted(h - l for l, h in zip(lo, hi))
        if long_ < 4 * max(mid, 1e-6):
            continue
        pad = float_depth + thin
        if any(all(lo[i] - pad <= wh[i] and wl[i] <= hi[i] + pad for i in range(3)) for wl, wh in boxes):
            out.append(obj.name.split("~")[0])
    return out


def collect(parts, mats, surface, quality, floaters=(), internal=(), float_depth=0.08):
    """Per-part facts BEFORE the join: small-detail count, material zones by surface area, contrast, surface story."""
    areas = {}
    total = 0.0
    diags = []
    markings = False
    import numpy as np  # noqa: PLC0415

    for obj, _group in parts:
        me = obj.data
        # every FACE's own material (a.zone's panels, a stump's sawn top, a grip's texture: a part's first material
        # alone missed them — measure 8), its area at the object's scale squared
        k2 = max(obj.matrix_world.to_scale()) ** 2
        n = len(me.polygons)
        if not n:
            continue
        fa = np.empty(n)
        me.polygons.foreach_get("area", fa)
        mi = np.empty(n, dtype=np.int64)
        me.polygons.foreach_get("material_index", mi)
        slots = [m_.name if m_ is not None else "?" for m_ in me.materials] or ["?"]
        per = np.bincount(np.clip(mi, 0, len(slots) - 1), weights=fa * k2, minlength=len(slots))
        for name, a in zip(slots, per.tolist()):
            if a > 0:
                areas[name] = areas.get(name, 0.0) + a
        total += float(per.sum())
        corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
        d = (Vector((max(c.x for c in corners), max(c.y for c in corners), max(c.z for c in corners)))
             - Vector((min(c.x for c in corners), min(c.y for c in corners), min(c.z for c in corners)))).length
        diags.append(d)
        low = obj.name.lower()
        if any(k in low for k in MARKING_WORDS):
            markings = True
    model_diag = max(diags) if diags else 1
    small = sum(1 for d in diags if d < model_diag * 0.06)
    import re

    costs = {}
    internal_tris = 0
    for obj, _g in parts:
        if obj.name.split("~")[0] in internal:  # enclosed mechanism parts: never seen, not the visible budget
            internal_tris += sum(len(p.vertices) - 2 for p in obj.data.polygons)
            continue
        base = re.sub(r"(~m\d+)$", "", obj.name)
        base = re.sub(r"([LR]?\d*)$", "", base) or obj.name
        costs[base] = costs.get(base, 0) + sum(len(p.vertices) - 2 for p in obj.data.polygons)
    top_costs = sorted(costs.items(), key=lambda kv: -kv[1])[:5]
    kinds = set()
    for obj, _g in floaters:  # baked detail is detail: its kinds count
        base = re.sub(r"(~m\d+)$", "", obj.name)
        base = re.sub(r"(\d+|[LR]\d*)$", "", base)
        kinds.add(re.sub(r"(\d+|[LR])$", "", base).lower())
    for (obj, _g), d in zip(parts, diags):
        if d < model_diag * 0.12:
            base = re.sub(r"(~m\d+)$", "", obj.name)
            base = re.sub(r"(\d+|[LR]\d*)$", "", base)
            base = re.sub(r"(\d+|[LR])$", "", base)
            kinds.add(base.lower())
    zones = [mname for mname, a in areas.items() if total and a / total >= 0.03]
    # how much of the model is WOOD (by pattern="wood", or by what its material is called): wood obeys wood's rules.
    # Counted per FACE (a part fused of steel and wood is wood where its wood is) over the parts that are SEEN (an
    # internal block is never looked at — and must not water down how much of the wood is carved)
    # The walls carved into wood (face layer kit_wood_cut, set by rbx.cut) are measured HERE, on the final mesh: a wall a
    # later cut removed is gone, a hidden part's walls are not seen; the walls in a non-wood material (a dark groove's)
    # join the wood's surface — they are its own carved surface (counted out, carving could carve a model out of being
    # wooden: the score-chased crate's 289 dark grooves left 24% wood, the line is 25%)
    wood = _wood_names(mats)
    wood_area = seen_total = carved_area = carved_other = sculpt_area = import_area = 0.0
    for obj, _g in parts:
        if obj.name.split("~")[0] in internal:
            continue
        me = obj.data
        k2 = max(obj.matrix_world.to_scale()) ** 2
        seen_total += sum(p.area for p in me.polygons) * k2
        if obj.get("kit_sculpt"):   # (an organic form: a.sculpt's parts)
            sculpt_area += sum(p.area for p in me.polygons) * k2
        elif obj.get("kit_import"):   # (an imported mesh: organic only when the asset says form="organic")
            import_area += sum(p.area for p in me.polygons) * k2
        slots = {i for i, m_ in enumerate(me.materials) if m_ is not None and m_.name in wood}
        if slots:
            wood_area += sum(p.area for p in me.polygons if p.material_index in slots) * k2
        layer = me.attributes.get("kit_wood_cut")
        if layer is not None and layer.domain == "FACE" and len(layer.data) == len(me.polygons):
            for p, v in zip(me.polygons, layer.data):
                if v.value:
                    carved_area += p.area * k2
                    if p.material_index not in slots:
                        carved_other += p.area * k2
    wood_share = wood_area / seen_total if seen_total else 0.0
    lines = wood_lines(parts, mats, floaters, internal, float_depth)
    lums = []
    for v in mats.values():
        if v["mat"].name in zones:
            c = v["color"]
            lums.append(0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2])
    contrast = (max(lums) - min(lums)) if len(lums) > 1 else 0.0
    story = 0.0
    story += 0.25 if (surface.get("edge_radius") is None or surface.get("edge_radius") > 0) else 0  # None = scale-aware auto
    story += 0.2 if surface.get("ao", 0) > 0 else 0
    story += 0.15 if surface.get("edge_wear", 0) > 0 else 0
    story += 0.2 if any(v.get("chip", 0) > 0 for v in mats.values()) else 0
    story += 0.2 if any(v.get("grime", 0) > 0 or v.get("wear", 0) > 0 for v in mats.values()) else 0
    return {
        "internal_tris": internal_tris,
        "small": small,
        "costs": top_costs,
        "kinds": len(kinds),
        "zones": len(zones),
        "contrast": contrast,
        "surface": min(1.0, story),
        "markings": markings,
        "wood_share": wood_share,
        "organic": round(sculpt_area / seen_total, 3) if seen_total else 0.0,
        "imported": round(import_area / seen_total, 3) if seen_total else 0.0,
        "wood_area": wood_area,
        "seen_area": seen_total,
        "carved_area": carved_area,
        "carved_other_area": carved_other,
        "wood_lines": len(lines),
        "wood_line_names": sorted(set(lines))[:3],
    }
