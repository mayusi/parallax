"""kit world meshes — world assets as real meshes, made in Blender from recipes (run by Blender, background).

    blender -b --factory-startup --python-exit-code 2 -P kit/world/meshes_blender.py -- <recipes.json> <out_dir>

A recipe: { "name": "oak_a", "kind": "tree" | "rock" | "cliff" | "wall", "seed": 3, ...kind's params }.
  tree : "grammar": "broadleaf" | "conifer" | "dead" | "shrub" (or a kind: kit/world/lsystem.py) grows its wood by
         an L-system; without it the older tree:
         height, trunk (radius), lean, branches, crown ("round" | "tall" | "umbrella" | "weeping"), leaf (card size),
         density, bark [r,g,b], leaves [[r,g,b], ...] (a few greens / autumn tones)
  rock : size [x, y, z], roughness, facets (0..1: how crisp), strata (0..1: layered bands)
  cliff: size [x, y, z] (a tall slab of layered rock), roughness, strata
  wall : modular castle masonry (kit/world/castle_blender.py): length, thick, seed, stone [r,g,b], bays, arch_r,
         corbels, parapet, back - every block modelled + its own tile of a stone atlas; modules tile seamlessly
         ruin (0..1: fallen merlons, a breach at breach_x), roots [{path: [[x, z], ...], r}] (blocks lifted round a root)
  tower: a round tower (radius, height, slits, ruin): curved ashlar, batter, slits, machicolations, parapet ring
  roof : a conical roof of slates (radius, height, slate [r,g,b]) with an eave and a finial
  cairn: stacked field stones (stones, base, seed): one per traveller at a Site of Grace
  root : the Erdtree's root (path [[x,y,z]...], radius [a,b], strands, twist, glow): braided bark + <name>_glow.fbx fissures (Neon)
Writes per asset: <name>.fbx (Roblox: pre-turned 180 deg about Blender Z, the measured import turn), <name>.png (the
texture atlas: bark | leaf clusters, trees only), <name>.mesh.json (positions / normals / uvs / indices for the web
viewer), <name>.preview.png (a 512 px render) and <out_dir>/meshes.json (name -> size, tris, files). One JSON line.

Why leaf CARDS with canopy normals: a tree read from a distance is its crown's silhouette and its soft light; cards
give the broken silhouette, normals pointing out from the crown's centre give the soft light (no card-by-card
facets). Rocks are displaced then decimated to planes: crisp facets read as stone at Roblox's scale.
"""

import base64
import json
import math
import os
import random
import struct
import sys

import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Vector

MAX_TRIS = 9000  # (Roblox accepts more; a forest of these must stay light)
ATLAS = 1024


# ------------------------------------------------------------------ noise (numpy, deterministic)
def hash3(p, seed):
    p = np.asarray(p, dtype=np.float64)
    h = np.sin(p[..., 0] * 127.1 + p[..., 1] * 311.7 + p[..., 2] * 74.7 + seed * 19.19) * 43758.5453
    return h - np.floor(h)


def vnoise3(p, seed):
    p = np.asarray(p, dtype=np.float64)
    i = np.floor(p)
    f = p - i
    u = f * f * (3 - 2 * f)
    acc = 0.0
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                w = (u[..., 0] if dx else 1 - u[..., 0]) * (u[..., 1] if dy else 1 - u[..., 1]) * (u[..., 2] if dz else 1 - u[..., 2])
                acc = acc + w * hash3(i + np.array([dx, dy, dz]), seed)
    return acc


def fbm3(p, seed, octaves=4):
    a, s, q = 0.5, 0.0, np.asarray(p, dtype=np.float64)
    for k in range(octaves):
        s = s + a * vnoise3(q, seed + k * 7)
        q = q * 2.03 + 11.7
        a *= 0.5
    return s


# ------------------------------------------------------------------ geometry container
class Geo:
    def __init__(self):
        self.v, self.n, self.uv, self.f = [], [], [], []

    def vert(self, p, n, uv):
        self.v.append(tuple(p))
        self.n.append(tuple(n))
        self.uv.append(tuple(uv))
        return len(self.v) - 1

    def tri(self, a, b, c):
        self.f.append((a, b, c))


def norm(v):
    v = np.asarray(v, dtype=float)
    l = np.linalg.norm(v)
    return v / l if l > 1e-9 else v


# ------------------------------------------------------------------ trees
def tube(g, pts, radii, sides, u0, u1, rng_len):
    """a tapering tube along pts (parallel-transport frames); bark UVs in [u0, u1] x [0, 1]"""
    pts = [np.asarray(p, float) for p in pts]
    tang = [norm(pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]) for i in range(len(pts))]
    ref = np.array([1.0, 0.0, 0.0]) if abs(tang[0][0]) < 0.9 else np.array([0.0, 0.0, 1.0])
    nrm = norm(np.cross(tang[0], ref))
    rings, along = [], 0.0
    for i, p in enumerate(pts):
        if i > 0:  # parallel transport the frame
            t0, t1 = tang[i - 1], tang[i]
            ax = np.cross(t0, t1)
            if np.linalg.norm(ax) > 1e-6:
                ang = math.acos(max(-1, min(1, float(np.dot(t0, t1)))))
                R = np.array(Matrix.Rotation(ang, 3, Vector(norm(ax))))
                nrm = norm(R @ nrm)
            along += float(np.linalg.norm(pts[i] - pts[i - 1]))
        bin_ = np.cross(tang[i], nrm)
        ring = []
        for k in range(sides + 1):
            a = k / sides * math.tau
            d = math.cos(a) * nrm + math.sin(a) * bin_
            ring.append(g.vert(p + d * radii[i], d, (u0 + (u1 - u0) * k / sides, min(along / rng_len, 1.0))))
        rings.append(ring)
    for i in range(len(rings) - 1):
        for k in range(sides):
            a, b, c, d = rings[i][k], rings[i][k + 1], rings[i + 1][k], rings[i + 1][k + 1]
            g.tri(a, c, b)
            g.tri(b, c, d)


def branch_path(start, direction, length, segs, up, wobble, rng):
    pts, d, p = [np.asarray(start, float)], norm(direction), np.asarray(start, float)
    for _ in range(segs):
        d = norm(d + np.array([rng.uniform(-wobble, wobble), up + rng.uniform(-wobble, wobble) * 0.5, rng.uniform(-wobble, wobble)]))
        p = p + d * (length / segs)
        pts.append(p)
    return pts


def build_tree(rec):
    rng = random.Random(rec.get("seed", 1))
    H = float(rec.get("height", 30))
    r0 = float(rec.get("trunk", H * 0.045))
    crown = rec.get("crown", "round")
    g = Geo()
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import lsystem  # noqa: E402

    if lsystem.wanted(rec) is not None:
        # GROWN BY A GRAMMAR (kit/world/lsystem.py; the owner's method list: L-system plant generation): the wood is
        # the plant the kind's rules grow - forks, whorls, a leader - in place of the limbs at chance angles below.
        # Each piece of wood is a tapering tube with a slight bend; the leaf cards hang on the grammar's leaf masses.
        plant, why = lsystem.grow(lsystem.wanted(rec), H, rec.get("seed", 1), r0)
        if plant is None:
            raise ValueError(f'{rec.get("name", "tree")}: its "grammar" cannot be grown - {why}')
        anchors = []
        for w in plant["wood"]:
            a, b = np.array(w["from"], float), np.array(w["to"], float)
            if w["foot"]:  # (every stem that starts on the ground - a shrub has several - goes into it)
                a = a - norm(b - a) * 1.0
            length = float(np.linalg.norm(b - a))
            # a slight bend, sideways to the piece (none at its two ends: pieces meet where the grammar says)
            side = norm(np.cross(b - a, np.array([rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1)])))
            bend = length * 0.04 * rng.uniform(-1, 1)
            ts = [0.0, 0.34, 0.67, 1.0]
            pts = [a + (b - a) * t + side * bend * math.sin(math.pi * t) for t in ts]
            radii = [w["radius"] + (w["tip"] - w["radius"]) * t for t in ts]
            if w["foot"]:
                radii[0] *= 1.25  # (the root flare)
            sides = 9 if w["depth"] == 0 else (6 if w["depth"] == 1 else 5)
            tube(g, pts, radii, sides, 0.0, 0.5, H * 0.7)
        anchors = [np.array(leaf["pos"], float) for leaf in plant["leaves"]]
        if anchors:  # (a leafy kind is in leaf ALONG its boughs, not only at their tips: a bough with a tuft at
            # its end read as a pole with arms)
            for w in plant["wood"]:
                if w["depth"] >= 1:
                    a, b = np.array(w["from"], float), np.array(w["to"], float)
                    reach = float(np.linalg.norm(b - a))
                    for t in (0.45, 0.75) if reach > H * 0.12 else (0.6,):
                        anchors.append(a + (b - a) * t)
        return _leaf_cards(rec, g, anchors, H, crown, rng)
    # trunk: a slight S-lean, tapering
    lean = np.array(rec.get("lean", [rng.uniform(-0.08, 0.08), rng.uniform(-0.08, 0.08)]))
    trunk_top = 0.62 if crown != "tall" else 0.78
    trunk = [np.array([lean[0] * H * t * t + math.sin(t * 3 + rng.random()) * 0.02 * H, H * trunk_top * t, lean[1] * H * t * t]) for t in np.linspace(0, 1, 7)]
    trunk[0] = trunk[0] - np.array([0, 1.0, 0])  # (into the ground)
    tube(g, trunk, [r0 * (1.25 - 0.6 * t) for t in np.linspace(0, 1, 7)], 9, 0.0, 0.5, H * 0.7)
    anchors = []  # (point, outward hint) where leaf clusters go
    nb = int(rec.get("branches", 6))
    golden = math.pi * (3 - math.sqrt(5))
    for b in range(nb):
        t = 0.45 + 0.55 * (b + rng.random() * 0.5) / nb
        idx = min(int(t * (len(trunk) - 1)), len(trunk) - 2)
        f = t * (len(trunk) - 1) - idx
        start = trunk[idx] * (1 - f) + trunk[idx + 1] * f
        az = b * golden + rng.uniform(-0.3, 0.3)
        elev = {"umbrella": 0.25, "weeping": 0.45, "tall": 0.85}.get(crown, 0.55) + rng.uniform(-0.15, 0.15)
        d = np.array([math.cos(az) * math.cos(elev), math.sin(elev), math.sin(az) * math.cos(elev)])
        L = H * {"umbrella": 0.5, "tall": 0.26}.get(crown, 0.38) * (1.15 - 0.5 * t) * rng.uniform(0.85, 1.15)
        up = {"weeping": -0.12, "umbrella": 0.02}.get(crown, 0.08)
        pts = branch_path(start, d, L, 5, up, 0.18, rng)
        rb = r0 * 0.55 * (1.1 - 0.5 * t)
        tube(g, pts, [rb * (1 - 0.8 * k / 5) + 0.05 for k in range(6)], 6, 0.0, 0.5, H * 0.7)
        # sub-branches and the leaf anchors along the outer part
        for s in range(rng.randint(2, 4)):
            ts = rng.uniform(0.35, 0.9)
            k = min(int(ts * 5), 4)
            sp = pts[k] * (1 - (ts * 5 - k)) + pts[k + 1] * (ts * 5 - k)
            sd = norm(d + np.array([rng.uniform(-0.9, 0.9), rng.uniform(-0.2, 0.5), rng.uniform(-0.9, 0.9)]))
            spts = branch_path(sp, sd, L * 0.45, 3, up, 0.25, rng)
            tube(g, spts, [rb * 0.45 * (1 - 0.8 * q / 3) + 0.04 for q in range(4)], 5, 0.0, 0.5, H * 0.7)
            anchors += [spts[q] for q in (2, 3)]
        anchors += [pts[q] for q in (3, 4, 5)]
    if crown == "tall":  # a leader up the middle
        anchors += [trunk[-1] + np.array([0, H * 0.12 * q, 0]) for q in range(3)]
    return _leaf_cards(rec, g, anchors, H, crown, rng)


def _leaf_cards(rec, g, anchors, H, crown, rng):
    """the leaf cards round each anchor (shared by the grown and the older tree) -> (geo, atlas image)"""
    tint = rec.get("leaves", [[86, 112, 52]])
    if len(anchors) == 0:  # (a bare tree: wood only)
        return g, atlas_tree(rec, tint)
    anchors = np.array(anchors)
    center = anchors.mean(axis=0)
    # leaf cards: clusters around each anchor, normals pointing out of the crown (soft, round light)
    size = float(rec.get("leaf", H * 0.09))
    per = int(rec.get("density", 7))
    for a in anchors if per > 0 else []:
        for _ in range(per):
            c = a + np.array([rng.gauss(0, size * 0.55), rng.gauss(0, size * 0.4), rng.gauss(0, size * 0.55)])
            if crown == "weeping":
                c = c - np.array([0, rng.uniform(0, size * 1.2), 0])
            out = norm(c - center + np.array([0, (H * 0.1), 0]))
            # a random card orientation, biased to face out
            axis1 = norm(np.cross(out, np.array([rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1)])))
            axis2 = norm(np.cross(out, axis1))
            s = size * rng.uniform(0.8, 1.25)
            quad = rng.randrange(4)  # which of the 4 leaf-cluster drawings
            qu, qv = 0.5 + 0.25 * (quad % 2), 0.5 * (quad // 2)
            corners = [c + (-axis1 - axis2) * s / 2, c + (axis1 - axis2) * s / 2, c + (axis1 + axis2) * s / 2, c + (-axis1 + axis2) * s / 2]
            uvs = [(qu, qv), (qu + 0.25, qv), (qu + 0.25, qv + 0.5), (qu, qv + 0.5)]
            # both faces (MeshParts are single-sided): the back copy wound the other way, same outward normal
            for flip in (False, True):
                ids = [g.vert(p, out, uv) for p, uv in zip(corners, uvs)]
                if flip:
                    g.tri(ids[0], ids[2], ids[1])
                    g.tri(ids[0], ids[3], ids[2])
                else:
                    g.tri(ids[0], ids[1], ids[2])
                    g.tri(ids[0], ids[2], ids[3])
    return g, atlas_tree(rec, tint)


def atlas_tree(rec, tints):
    """the texture: bark on the left half (vertical fibres + grooves), 4 leaf-cluster drawings on the right (alpha)"""
    rng = np.random.default_rng(rec.get("seed", 1))
    img = np.zeros((ATLAS, ATLAS, 4), dtype=np.float32)
    bark = np.array(rec.get("bark", [86, 70, 54]), float) / 255
    ys, xs = np.mgrid[0:ATLAS, 0:ATLAS // 2]
    fib = fbm3(np.stack([xs / 9.0, ys / 90.0, np.zeros_like(xs, dtype=float)], -1), 5, 4)
    groove = np.abs(np.sin(xs / 512 * math.tau * 7 + fib * 5))
    shade = (0.55 + 0.6 * fib) * (0.62 + 0.38 * groove)
    img[:, : ATLAS // 2, :3] = bark[None, None, :] * shade[..., None]
    img[:, : ATLAS // 2, 3] = 1
    # leaves: each quadrant a cluster of ~70 leaves, ellipses with a darker midrib, colours jittered among the tints
    tints = [np.array(t, float) / 255 for t in tints]
    for q in range(4):
        ox, oy = ATLAS // 2 + (q % 2) * (ATLAS // 4), (q // 2) * (ATLAS // 2)
        w, h = ATLAS // 4, ATLAS // 2
        shape = rec.get("leafShape", "broad")
        for _ in range(110 if shape == "broad" else 80):
            cx, cy = rng.normal(w / 2, w * 0.19), rng.normal(h / 2, h * 0.19)
            L, W = (rng.uniform(17, 27), rng.uniform(12, 18)) if shape == "broad" else (rng.uniform(22, 40), rng.uniform(7, 11))
            ang = rng.uniform(0, math.pi)
            x0, x1 = int(max(0, cx - L)), int(min(w, cx + L))
            y0, y1 = int(max(0, cy - L)), int(min(h, cy + L))
            if x1 <= x0 or y1 <= y0:
                continue
            yy, xx = np.mgrid[y0:y1, x0:x1]
            dx, dy = xx - cx, yy - cy
            u = dx * math.cos(ang) + dy * math.sin(ang)
            v = -dx * math.sin(ang) + dy * math.cos(ang)
            inside = (u / L) ** 2 + (v / W) ** 2 < 1
            col = tints[rng.integers(len(tints))] * rng.uniform(0.75, 1.15)
            light = 0.8 + 0.35 * (1 - np.abs(v) / W) - 0.25 * (np.abs(v) < 1.2)  # rounded, a midrib
            reg = img[oy + y0: oy + y1, ox + x0: ox + x1]
            reg[inside, :3] = np.clip(col[None, :] * light[inside][:, None], 0, 1)
            reg[inside, 3] = 1
    return img


# ------------------------------------------------------------------ rocks and cliffs
def build_rock(rec, cliff=False):
    seed = rec.get("seed", 1)
    size = np.array(rec.get("size", [10, 7, 9] if not cliff else [30, 50, 14]), float)
    rough = float(rec.get("roughness", 0.35))
    strata = float(rec.get("strata", 0.4 if cliff else 0.1))
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=4, radius=1.0)
    for v in bm.verts:
        p = np.array(v.co)
        n = norm(p)
        d = (fbm3(p * 1.4, seed, 4) - 0.5) * 2 * rough + (fbm3(p * 4.2, seed + 9, 3) - 0.5) * rough * 0.4
        if strata > 0:  # horizontal layers stepping in and out
            d += strata * 0.18 * math.floor((p[2] * 3.5 + fbm3(p * 0.8, seed + 3, 2) * 2) % 2)
        p = n * (1 + d)
        p[2] = max(p[2], -0.55)  # a flat-ish base to sit on the land
        v.co = Vector(p * size[[0, 2, 1]] / 2)  # (Blender is Z-up: size is [x, y(up), z])
    me = bpy.data.meshes.new("rock")
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(rec["name"], me)
    bpy.context.collection.objects.link(obj)
    dec = obj.modifiers.new("dec", "DECIMATE")
    dec.ratio = 0.22 + 0.25 * (1 - float(rec.get("facets", 0.7)))
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier="dec")
    for p in obj.data.polygons:
        p.use_smooth = False  # crisp facets
    return obj


# ------------------------------------------------------------------ Blender objects, export, preview
def geo_to_object(name, g, img):
    me = bpy.data.meshes.new(name)
    # Blender is Z-up: (x, y_up, z) -> (x, -z, y)
    verts = [(x, -z, y) for (x, y, z) in g.v]
    me.from_pydata(verts, [], g.f)
    me.update()
    uv = me.uv_layers.new(name="UV")
    for poly in me.polygons:
        for li in poly.loop_indices:
            uv.data[li].uv = g.uv[me.loops[li].vertex_index]
    me.normals_split_custom_set([(n[0], -n[2], n[1]) for n in [g.n[me.loops[i].vertex_index] for i in range(len(me.loops))]])
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    if img is not None:
        _texture(obj, img, name)
    return obj


def _texture(obj, img, name):
    """the atlas as the object's one material (the preview renders it; Roblox gets the PNG as TextureID)"""
    im = bpy.data.images.new(name + "_atlas", img.shape[1], img.shape[0], alpha=True)
    im.pixels.foreach_set(np.flipud(img).ravel())  # (Blender images are bottom-up)
    mat = bpy.data.materials.new(name + "_mat")
    mat.use_nodes = True
    nt = mat.node_tree
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = im
    bsdf = nt.nodes.get("Principled BSDF")
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
    try:
        mat.blend_method = "CLIP"
    except AttributeError:
        pass
    obj.data.materials.append(mat)


def _w3_object(name, part, out):
    """a W3 module part (kit/world/modkit_facade.py: Roblox axes) as a Blender object wearing its trim sheet's maps
    (colour + normal + roughness from <out>/kit_trim_<sheet>_*.png: the preview shows what a SurfaceAppearance will)"""
    me = bpy.data.meshes.new(name)
    me.from_pydata([(x, -z, y) for x, y, z in part["verts"]], [], [tuple(f) for f in part["faces"]])
    me.update()
    uvl = me.uv_layers.new(name="UV")
    for poly in me.polygons:
        for li in poly.loop_indices:
            uvl.data[li].uv = part["uvs"][me.loops[li].vertex_index]
        poly.use_smooth = False
    mat = bpy.data.materials.new(f"trim_{part['sheet']}")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    for m, socket in (("color", "Base Color"), ("roughness", "Roughness"), ("normal", None)):
        node = nt.nodes.new("ShaderNodeTexImage")
        node.image = bpy.data.images.load(os.path.join(out, f"kit_trim_{part['sheet']}_{m}.png"))
        if m != "color":
            node.image.colorspace_settings.name = "Non-Color"
        if socket:
            nt.links.new(node.outputs["Color"], bsdf.inputs[socket])
        else:
            nm = nt.nodes.new("ShaderNodeNormalMap")
            nt.links.new(node.outputs["Color"], nm.inputs["Color"])
            nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    me.materials.append(mat)
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj


def save_png(img, path):
    im = bpy.data.images.new(os.path.basename(path), img.shape[1], img.shape[0], alpha=True)
    im.pixels.foreach_set(np.flipud(img).ravel())
    im.filepath_raw = path
    im.file_format = "PNG"
    im.save()


def mesh_json(obj, path, textured):
    """the viewer's copy: positions / normals / uvs / indices, Roblox-space (y up), little-endian base64"""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    me.calc_loop_triangles()
    uv = me.uv_layers.active.data if me.uv_layers.active else None
    pos, nrm, uvs, idx = [], [], [], []
    corner = me.corner_normals if hasattr(me, "corner_normals") else None
    for tri in me.loop_triangles:
        for li in tri.loops:
            v = me.vertices[me.loops[li].vertex_index].co
            n = corner[li].vector if corner is not None else me.loops[li].normal
            if not textured:
                n = tri.normal  # (rocks: flat facets)
            pos += [v.x, v.z, -v.y]
            nrm += [n.x, n.z, -n.y]
            uvs += list(uv[li].uv) if uv else [0, 0]
            idx.append(len(idx))
    ev.to_mesh_clear()
    b64 = lambda fmt, a: base64.b64encode(struct.pack(f"<{len(a)}{fmt}", *a)).decode()
    xs, ys, zs = pos[0::3], pos[1::3], pos[2::3]
    data = {"tris": len(idx) // 3, "min": [min(xs), min(ys), min(zs)], "max": [max(xs), max(ys), max(zs)],
            "position": b64("f", pos), "normal": b64("f", nrm), "uv": b64("f", uvs)}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    return data


def preview(obj, path, textured):
    scene = bpy.context.scene
    for o in list(scene.objects):
        o.hide_render = o is not obj
    # Cycles on the CPU: no GPU context (EEVEE re-initialised per asset crashed the NVIDIA GL driver here)
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 24
    scene.cycles.use_denoising = False
    scene.render.resolution_x = scene.render.resolution_y = 512
    scene.render.film_transparent = False
    world = bpy.data.worlds.new("w") if not scene.world else scene.world
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs[0].default_value = (0.55, 0.62, 0.72, 1)
    bg.inputs[1].default_value = 0.8
    if not textured:
        mat = bpy.data.materials.new("rockmat")
        mat.use_nodes = True
        mat.node_tree.nodes.get("Principled BSDF").inputs["Base Color"].default_value = (0.42, 0.40, 0.37, 1)
        obj.data.materials.clear()
        obj.data.materials.append(mat)
    sun = bpy.data.lights.new("sun", "SUN")
    sun.energy = 4
    so = bpy.data.objects.new("sun", sun)
    so.rotation_euler = (math.radians(50), math.radians(10), math.radians(35))
    scene.collection.objects.link(so)
    bpy.context.view_layer.update()  # (the bounds go stale after the export's turn-and-restore: the camera framed nothing)
    bb = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    lo = Vector((min(v.x for v in bb), min(v.y for v in bb), min(v.z for v in bb)))
    hi = Vector((max(v.x for v in bb), max(v.y for v in bb), max(v.z for v in bb)))
    mid, span = (lo + hi) / 2, max((hi - lo).length, 1)
    cam = bpy.data.cameras.new("cam")
    cam.lens = 40
    co = bpy.data.objects.new("cam", cam)
    co.location = mid + Vector((span * 0.62, -span * 0.78, span * 0.22))
    co.rotation_euler = (mid - co.location).to_track_quat("-Z", "Y").to_euler()
    scene.collection.objects.link(co)
    scene.camera = co
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(so)
    bpy.data.objects.remove(co)


def export_fbx(obj, path):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    # Roblox's mesh import turns an FBX 180 deg about Y (measured, kit/vfx/meshes.py): pre-turn it, export, restore
    obj.data.transform(Matrix.Rotation(math.pi, 4, "Z"))
    try:
        bpy.ops.export_scene.fbx(filepath=path, use_selection=True, axis_forward="-Z", axis_up="Y", apply_unit_scale=True,
                                 apply_scale_options="FBX_SCALE_UNITS", bake_anim=False, add_leaf_bones=False,
                                 path_mode="COPY", embed_textures=False)
    finally:
        obj.data.transform(Matrix.Rotation(-math.pi, 4, "Z"))


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    recipes_path, out = argv[0], os.path.abspath(argv[1])  # (Blender resolves relative paths against the .blend)
    only = argv[argv.index("--only") + 1].split(",") if "--only" in argv else None
    os.makedirs(out, exist_ok=True)
    recipes = json.load(open(recipes_path, encoding="utf-8"))
    reg_path = os.path.join(out, "meshes.json")
    reg = json.load(open(reg_path, encoding="utf-8")) if os.path.isfile(reg_path) else {}
    # the world meshes already uploaded into a game: the names in the project's committed ids file (--ids <path>)
    uploaded = set()
    if "--ids" in argv and os.path.isfile(argv[argv.index("--ids") + 1]):
        try:
            ids = json.load(open(argv[argv.index("--ids") + 1], encoding="utf-8"))
            uploaded = set((ids.get("worldmeshes") or {}).keys()) if isinstance(ids, dict) else set()
        except (ValueError, OSError):
            uploaded = set()
    done, errors = [], []
    for rec in recipes:
        name = rec["name"]
        if only and name not in only:
            continue
        bpy.ops.wm.read_factory_settings(use_empty=True)
        kind = rec.get("kind", "tree")
        textured = kind == "tree"
        if kind == "tree":
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import lsystem  # noqa: E402

            # (a tree says how its wood grows; one already uploaded into a game is not asked)
            ask = lsystem.unsaid(rec, uploaded)
            if ask:
                errors.append(ask)
                continue
            try:
                g, img = build_tree(rec)
            except ValueError as e:  # (a grammar that cannot be grown, a number that is none)
                errors.append(str(e))
                continue
            obj = geo_to_object(name, g, img)
            save_png(img, os.path.join(out, name + ".png"))
        elif kind in ("rock", "cliff"):
            obj = build_rock(rec, cliff=kind == "cliff")
        elif kind == "root":
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import castle_blender  # noqa: E402

            textured = True
            obj, img, gobj = castle_blender.build_root(rec)
            _texture(obj, img, name)
            save_png(img, os.path.join(out, name + ".png"))
            export_fbx(gobj, os.path.join(out, name + "_glow.fbx"))  # (Neon in Roblox: the light lives in the cracks)
            gdata = mesh_json(gobj, os.path.join(out, name + "_glow.mesh.json"), False)
        elif kind in ("wall", "tower", "roof", "cairn"):
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import castle_blender  # noqa: E402

            textured = True
            obj, img = castle_blender.build_piece(rec)
            _texture(obj, img, name)
            save_png(img, os.path.join(out, name + ".png"))
        elif kind == "gothic_module" and rec.get("kit") == "w3":
            # a facade module cut from the W3 kit (kit/world/modkit_facade.py): one mesh a trim sheet, every one
            # mapped on the two SHARED sheets (kit/world/trims.py, written once into out_dir) - no atlas of its own
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import modkit_facade  # noqa: E402
            import trims  # noqa: E402

            textured = True
            try:
                cut = modkit_facade.module(rec)
            except ValueError as e:
                errors.append(f"{name}: {e}")
                continue
            here = os.path.dirname(os.path.abspath(__file__))
            trims.ensure(out, sources=[os.path.join(here, "modkit.py")])
            objs = []
            for k, part in enumerate(cut["parts"]):
                pname = name if k == 0 else f"{name}__{part['sheet']}"
                objs.append((pname, part["sheet"], _w3_object(pname, part, out)))
            obj = objs[0][2]
            w3_sheet = objs[0][1]
            w3_extra = []
            for pname, sheet, pobj in objs[1:]:
                ptris = sum(len(p.vertices) - 2 for p in pobj.data.polygons)
                pdata = mesh_json(pobj, os.path.join(out, pname + ".mesh.json"), True)
                export_fbx(pobj, os.path.join(out, pname + ".fbx"))
                reg[pname] = {"kind": "gothic_module_part", "tris": pdata["tris"], "min": pdata["min"],
                              "size": [round(pdata["max"][i] - pdata["min"][i], 3) for i in range(3)],
                              "textured": True, "fbx": pname + ".fbx", "texture": None, "trim": sheet, "of": name}
                if ptris > MAX_TRIS:
                    errors.append(f"{pname}: {ptris} tris > {MAX_TRIS}")
                w3_extra.append(pname)
        elif kind in ("gothic_house", "gothic_module", "gothic_bay", "gothic_lamppost", "gothic_well", "gothic_spire", "gothic_turret",
                      "gothic_quoin"):
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import gothic_blender  # noqa: E402

            textured = True
            obj, img = gothic_blender.build_piece(rec)
            _texture(obj, img, name)
            save_png(img, os.path.join(out, name + ".png"))
        elif kind == "hlod_ring":
            # a quarter of the far ranges as ONE proxy mesh (kit/world/hlod.py; V3 stage F.2): untextured, the
            # horizon step's palette colours it in Roblox
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import hlod  # noqa: E402

            try:
                verts, faces = hlod.ring(rec, int(rec.get("quadrant", 1)))
            except ValueError as e:  # (a ring too big for a MeshPart)
                errors.append(f"{name}: {e}")
                continue
            me = bpy.data.meshes.new(name)
            me.from_pydata([(x, -z, y) for x, y, z in verts], [], faces)  # (Roblox (x, y up, z) -> Blender (x, -z, y))
            me.update()
            obj = bpy.data.objects.new(name, me)
            bpy.context.collection.objects.link(obj)
        else:
            errors.append(f"{name}: unknown kind {kind!r} (tree | rock | cliff | wall | tower | roof | root | cairn | gothic_house | gothic_module | gothic_bay | gothic_lamppost | gothic_well | gothic_spire | gothic_turret | gothic_quoin | hlod_ring)")
            continue
        tris = sum(len(p.vertices) - 2 for p in obj.data.polygons)
        if tris > MAX_TRIS:
            errors.append(f"{name}: {tris} tris > {MAX_TRIS}")
        if kind == "hlod_ring":
            import hlod  # noqa: E402

            if tris > hlod.MAX_TRIS:
                errors.append(f"{name}: {tris} tris > an HLOD proxy's {hlod.MAX_TRIS}")
        data = mesh_json(obj, os.path.join(out, name + ".mesh.json"), textured)
        export_fbx(obj, os.path.join(out, name + ".fbx"))
        if kind == "gothic_module" and rec.get("kit") == "w3":
            # (the FBX exporter copies the trim maps the preview material reads into <name>.fbm/: the sheets are
            # uploaded once from out_dir, never a copy a module)
            import shutil  # noqa: PLC0415

            for stem in [name] + w3_extra:
                shutil.rmtree(os.path.join(out, stem + ".fbm"), ignore_errors=True)
        preview(obj, os.path.join(out, name + ".preview.png"), textured)
        size = [round(data["max"][i] - data["min"][i], 3) for i in range(3)]
        reg[name] = {"kind": kind, "tris": data["tris"], "size": size, "min": data["min"], "textured": textured,
                     "fbx": name + ".fbx", "texture": name + ".png" if textured else None}
        if kind == "root":
            reg[name]["glow"] = name + "_glow.fbx"
            # its own entry: the compiler places it like any mesh (untextured: the palette's Neon colours it in Roblox)
            reg[name + "_glow"] = {"kind": "glow", "tris": gdata["tris"], "min": gdata["min"],
                                   "size": [round(gdata["max"][i] - gdata["min"][i], 3) for i in range(3)],
                                   "textured": False, "fbx": name + "_glow.fbx", "texture": None}
        if kind == "gothic_module":
            # a facade module (kit/lib/worldfacade.luau): the compiler asks which kind it is, the storey height it is
            # cut for and the opening it leaves (Facade.problem), and places it by its recipe's own box
            reg[name]["module"] = rec.get("module")
            if rec.get("floorHeight") is not None:
                reg[name]["floorHeight"] = float(rec["floorHeight"])
            if isinstance(rec.get("gap"), dict):
                reg[name]["gap"] = {k: float(rec["gap"][k]) for k in ("width", "height", "sill") if k in rec["gap"]}
            reg[name]["box"] = [float(v) for v in rec.get("size", size)]
            if rec.get("kit") == "w3":
                # its look: the shared trim sheet it is mapped on (the compiler gives it that sheet's maps as a
                # SurfaceAppearance), and the meshes on the other sheet placed with it in the same frame
                reg[name]["texture"] = None
                reg[name]["trim"] = w3_sheet
                reg[name]["parts"] = w3_extra
                reg[name]["kit"] = "w3"
        if kind == "hlod_ring":
            reg[name]["hlod"] = {"quadrant": int(rec.get("quadrant", 1)), "radius": float(rec.get("radius", 1500))}
        if kind == "gothic_quoin":
            # one storey of one corner's quoins (kit/world/quoins.py): the compiler stands it at a skin's corners
            reg[name]["quoin"] = {"height": float(rec.get("height", 14)), "proj": float(rec.get("proj", 0.15))}
        if kind == "gothic_house":
            # compiler uses these for skin placement / opening alignment
            reg[name]["footprint"] = [float(rec.get("width", 22)), float(rec.get("depth", 22))]
            if isinstance(rec.get("quoins"), str) and rec["quoins"]:
                reg[name]["quoins"] = rec["quoins"]  # (its corner quoins: a gothic_quoin strip, never stripped)
            reg[name]["floors"] = int(rec.get("floors", 4))
            reg[name]["floorHeight"] = float(rec.get("floorHeight", 14))
            win_cfg = rec.get("windows", {})
            reg[name]["windows"] = {
                "every": float(win_cfg.get("every", 10)),
                "width": float(win_cfg.get("width", 3.4)),
                "height": float(win_cfg.get("height", 7)),
                "sill": float(win_cfg.get("sill", 3.5)),
                "sides": win_cfg.get("sides", ["N", "E", "S", "W"]),
            }
            door_cfg = rec.get("door", {})
            reg[name]["door"] = {
                "side": door_cfg.get("side", "S"),
                "width": float(door_cfg.get("width", 5)),
                "height": float(door_cfg.get("height", 9)),
            }
        done.append(f"{name} ({data['tris']} tris)")
    json.dump(reg, open(reg_path, "w", encoding="utf-8"), indent=1)
    ok = not errors
    print(json.dumps({"status": "pass" if ok else "fail",
                      "summary": f"{len(done)} mesh(es): {', '.join(done)}" + (f"; {len(errors)} problem(s): {errors[0]}" if errors else ""),
                      "next_action": f"LOOK at {out}/<name>.preview.png" if ok else errors[0]}))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
