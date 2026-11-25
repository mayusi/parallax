"""fxlab.py — VFX elements rendered for real in Blender (Cycles GPU), frame by frame, for Roblox sprite sheets.

    blender -b --factory-startup --python-exit-code 2 -P kit/vfx/fxlab.py -- --specs assets/textures
            --out build/fxlab [--force] [name ...]

Roblox cannot run Blender's shaders or simulations, so Blender MAKES the element and Roblox PLAYS it: each spec
(assets/textures/<name>.json with "engine": "fx") names a recipe that builds a real scene — 3D light spikes, wind
ribbons around an axis, lit volumetric dust, shader-noise energy flows, a cracked glowing trench — and renders its
frames with transparency. Frames are written as HDR float16 arrays (build/fxlab/<name>/<i>.npy, linear, RGB
premultiplied by coverage, values above 1 kept) so kit/vfx/fxfinish.py can add glow / streaks, map the hot core to
white and pack the Roblox sheet. Only re-renders when the spec is newer than its frames (or --force).

Spec: {"engine": "fx", "recipe": "burst|wind|dust|flow|crack|blast|ring|wave|rays|lightning|slash|shards|cel|smoke_sim|fire_sim|shockwave|glyph|circle|blackhole|gradient|aura|import", "frames": 16, "cell": 256, "samples": 32,
       "seed": 1, "params": {...}}   (recipe params: see the RECIPES functions below; every one has defaults)
Prints one JSON line: {status, summary, next_action, renders:[{name, frames, seconds, rendered}]}.
"""

import json
import math
import os
import random
import sys
import time

import bmesh
import bpy
import numpy as np
from mathutils import Vector

# ---------------------------------------------------------------- args


def args():
    a = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    out = {"names": [], "force": False}
    i = 0
    while i < len(a):
        if a[i] == "--force":
            out["force"] = True
            i += 1
        elif a[i].startswith("--"):
            out[a[i][2:]] = a[i + 1]
            i += 2
        else:
            out["names"].append(a[i])
            i += 1
    return out


# ---------------------------------------------------------------- scene + shader helpers


def ease_out(k, p=2.0):
    k = min(max(k, 0.0), 1.0)
    return 1 - (1 - k) ** p


def smooth(a, b, x):
    t = min(max((x - a) / (b - a), 0.0), 1.0) if b != a else float(x >= a)
    return t * t * (3 - 2 * t)


def new_scene(w, h, samples, volume=False):
    bpy.ops.wm.read_homefile(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for dev in ("OPTIX", "CUDA"):
        try:
            prefs.compute_device_type = dev
            prefs.get_devices()
            break
        except Exception:  # noqa: BLE001
            continue
    for d in prefs.devices:
        d.use = d.type != "CPU"
    sc.cycles.device = "GPU" if any(d.use for d in prefs.devices) else "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.cycles.max_bounces = 4 if volume else 2
    sc.cycles.volume_bounces = 1 if volume else 0
    sc.cycles.volume_step_rate = 1.0
    sc.render.film_transparent = True
    sc.render.resolution_x, sc.render.resolution_y = w, h
    sc.render.resolution_percentage = 100
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.render.image_settings.file_format = "OPEN_EXR"
    sc.render.image_settings.color_depth = "16"
    sc.render.image_settings.color_mode = "RGBA"
    world = bpy.data.worlds.new("W")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[1].default_value = 0.0
    sc.world = world
    return sc


def camera(sc, ortho=None, loc=(0, -5, 0), look=(0, 0, 0), lens=50):
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.location = loc
    cam.rotation_euler = (Vector(look) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    if ortho:
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = ortho
    else:
        cam.data.lens = lens
    return cam


# the named key-light directions of a sim (the camera looks along +Y): its `light`, and the LIT VARIANTS rendered from the
# same bake (a spec {"recipe": "lit_variant", "of": <sim>, "light": <side>} - six-way lighting's Roblox stand-in)
LIGHTS = {"left": (0, -53, 0), "right": (0, 53, 0), "top": (0, 0, 0), "back": (-45, 0, 0), "front": (45, 0, 0)}


def sun(sc, energy, rot, color=(1, 1, 1)):
    ob = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    ob.data.energy = energy
    ob.data.color = color
    ob.rotation_euler = [math.radians(r) for r in rot]
    sc.collection.objects.link(ob)
    return ob


class Graph:
    """tiny shader-graph builder: g.n(type, input=value, prop=value), g.l(out_socket, in_socket)"""

    def __init__(self, name):
        self.mat = bpy.data.materials.new(name)
        self.mat.use_nodes = True
        self.nt = self.mat.node_tree
        for n in list(self.nt.nodes):
            self.nt.nodes.remove(n)
        self.out = self.nt.nodes.new("ShaderNodeOutputMaterial")

    def n(self, kind, **kw):
        node = self.nt.nodes.new(kind)
        for k, v in kw.items():  # node settings first (noise_dimensions decides which inputs exist)
            if not k[0].isupper():
                setattr(node, k, v)
        for k, v in kw.items():
            if k[0].isupper():
                node.inputs[k].default_value = v
        return node

    def l(self, a, b):  # noqa: E741
        self.nt.links.new(a, b)
        return b

    def math(self, op, a, b=None, clamp=False):
        m = self.n("ShaderNodeMath", operation=op)
        m.use_clamp = clamp
        for i, v in enumerate((a, b)):
            if v is None:
                continue
            if isinstance(v, (int, float)):
                m.inputs[i].default_value = v
            else:
                self.l(v, m.inputs[i])
        return m.outputs[0]

    def value(self, v):
        node = self.n("ShaderNodeValue")
        node.outputs[0].default_value = v
        return node

    def remap(self, x, a, b, c=0.0, d=1.0, clamp=True):
        m = self.n("ShaderNodeMapRange")
        m.clamp = clamp
        self.l(x, m.inputs["Value"])
        m.inputs["From Min"].default_value, m.inputs["From Max"].default_value = a, b
        m.inputs["To Min"].default_value, m.inputs["To Max"].default_value = c, d
        return m.outputs["Result"]

    def ramp(self, x, stops):
        """stops: [(pos, (r, g, b)), ...] -> color socket"""
        r = self.n("ShaderNodeValToRGB")
        self.l(x, r.inputs[0])
        els = r.color_ramp.elements
        while len(els) > len(stops):
            els.remove(els[-1])
        while len(els) < len(stops):
            els.new(0.5)
        for e, (p, c) in zip(els, stops):
            e.position = p
            e.color = (c[0], c[1], c[2], 1)
        return r.outputs["Color"]

    def emit_alpha(self, color, strength, alpha):
        """surface = emission(color * strength) where alpha, transparent elsewhere"""
        em = self.n("ShaderNodeEmission")
        self.l(color, em.inputs["Color"])
        if isinstance(strength, (int, float)):
            em.inputs["Strength"].default_value = strength
        else:
            self.l(strength, em.inputs["Strength"])
        tr = self.n("ShaderNodeBsdfTransparent")
        mix = self.n("ShaderNodeMixShader")
        if isinstance(alpha, (int, float)):
            mix.inputs["Factor"].default_value = alpha
        else:
            self.l(alpha, mix.inputs["Factor"])
        self.l(tr.outputs[0], mix.inputs[1])
        self.l(em.outputs[0], mix.inputs[2])
        self.l(mix.outputs[0], self.out.inputs["Surface"])


def mesh_object(sc, name, verts, faces, uvs=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    if uvs is not None:
        layer = me.uv_layers.new(name="UVMap")
        for poly in me.polygons:
            for li, vi in zip(poly.loop_indices, poly.vertices):
                layer.data[li].uv = uvs[vi]
    for p in me.polygons:
        p.use_smooth = True
    ob = bpy.data.objects.new(name, me)
    sc.collection.objects.link(ob)
    return ob


# ---------------------------------------------------------------- recipes
# each returns update(k) for k in 0..1 across the sheet; the scene is the current one.


def recipe_burst(sc, p, rng):
    """a 3D burst of light: hot core + spikes shooting out in every direction, seen face-on.
    params: spikes 28, length [0.45, 1.0], thick [0.03, 0.07], depth 0.35 (how much spikes point at the camera),
    core 0.2, hot 40 (core emission), heat 12 (spike emission), grow 0.16 (k when fully out), color_tip [r,g,b],
    fade 1.3 (how fast the spikes thin away: lower keeps them to the sheet's end, so no two last frames are empty)"""
    camera(sc, ortho=p.get("frame", 2.6), loc=(0, -6, 0))
    n = int(p.get("spikes", 28))
    lo, hi = p.get("length", [0.45, 1.0])
    tlo, thi = p.get("thick", [0.03, 0.07])
    depth = p.get("depth", 0.35)
    tip = p.get("color_tip", [1.0, 0.62, 0.18])
    # spike material: emission falls from base to tip (Generated z), colour white -> tip colour
    g = Graph("Spike")
    gen = g.n("ShaderNodeTexCoord").outputs["Generated"]
    z = g.n("ShaderNodeSeparateXYZ")
    g.l(gen, z.inputs[0])
    fall = g.math("POWER", g.math("SUBTRACT", 1.0, z.outputs["Z"], clamp=True), 1.6)
    spike_k = g.value(1.0)
    strength = g.math("MULTIPLY", g.math("MULTIPLY", fall, p.get("heat", 12.0)), spike_k.outputs[0])
    col = g.ramp(z.outputs["Z"], [(0.0, (1, 1, 1)), (0.35, (1.0, 0.93, 0.7)), (1.0, tuple(tip))])
    g.emit_alpha(col, strength, 1.0)
    spike_mat = g.mat
    # a unit cone with its base at the origin, pointing +Z
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=10, radius1=1.0, radius2=0.0, depth=1.0)
    bmesh.ops.translate(bm, verts=bm.verts, vec=(0, 0, 0.5))
    cone = bpy.data.meshes.new("Cone")
    bm.to_mesh(cone)
    bm.free()
    cone.materials.append(spike_mat)
    spikes = []
    for _ in range(n):
        v = np.array([rng.gauss(0, 1), rng.gauss(0, 1) * depth, rng.gauss(0, 1)])
        v /= np.linalg.norm(v) + 1e-9
        ob = bpy.data.objects.new("Spike", cone)
        sc.collection.objects.link(ob)
        ob.rotation_mode = "QUATERNION"
        ob.rotation_quaternion = _quat_from_z(v)
        spikes.append((ob, rng.uniform(lo, hi), rng.uniform(tlo, thi), rng.uniform(0.0, 0.08)))
    # core: a sphere bright where it faces the camera
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, segments=32, ring_count=16)
    core = bpy.context.active_object
    bpy.ops.object.shade_smooth()
    gc = Graph("Core")
    lw = gc.n("ShaderNodeLayerWeight", Blend=0.5)
    face = gc.math("SUBTRACT", 1.0, lw.outputs["Facing"], clamp=True)
    core_k = gc.value(1.0)
    cstr = gc.math("MULTIPLY", gc.math("POWER", face, 2.0), p.get("hot", 40.0))
    cstr = gc.math("MULTIPLY", cstr, core_k.outputs[0])
    ccol = gc.ramp(face, [(0.0, tuple(tip)), (0.5, (1.0, 0.9, 0.6)), (1.0, (1, 1, 1))])
    gc.emit_alpha(ccol, cstr, 1.0)
    core.data.materials.append(gc.mat)
    rcore = p.get("core", 0.2)
    grow_at = p.get("grow", 0.16)
    fade = p.get("fade", 1.3)  # how fast the spikes thin away (lower = they last to the sheet's end)

    def update(k):
        grow = ease_out(k / grow_at, 3)
        for ob, length, thick, lag in spikes:
            gk = ease_out((k - lag) / grow_at, 3)
            L = length * (0.12 + 0.88 * gk) * (1 + 0.18 * k)
            T = thick * (0.5 + 0.5 * gk) * (1 - k) ** fade + 1e-4
            ob.scale = (T, T, max(L, 1e-4))
        spike_k.outputs[0].default_value = (1 - k) ** 1.6
        s = rcore * (0.4 + 1.4 * grow) * max(0.0, 1 - k / 0.55) ** 1.5 + 1e-4
        core.scale = (s, s, s)
        core_k.outputs[0].default_value = max(0.0, 1 - k / 0.6) ** 1.2

    return update


def _quat_from_z(v):
    z = np.array([0.0, 0.0, 1.0])
    axis = np.cross(z, v)
    s = np.linalg.norm(axis)
    c = float(np.dot(z, v))
    if s < 1e-8:
        return (1, 0, 0, 0) if c > 0 else (0, 1, 0, 0)
    axis /= s
    ang = math.atan2(s, c)
    return (math.cos(ang / 2), *(axis * math.sin(ang / 2)))


def recipe_wind(sc, p, rng):
    """wind ribbons whipping around a vertical axis (a sword's wind barrier tearing open), seen from 3/4 above.
    params: arcs 8, radius [0.35, 0.9], height [-0.75, 0.75], span [110, 230] degrees, width [0.04, 0.12],
    spin 320 (degrees over the sheet), expand 0.7, tint [r, g, b], strength 4"""
    camera(sc, loc=(0, -p.get("distance", 3.0), p.get("distance", 3.0) * 0.36), look=(0, 0, 0.0), lens=46)
    tint = p.get("tint", [0.9, 0.97, 1.0])
    g = Graph("Wind")
    uv = g.n("ShaderNodeUVMap").outputs["UV"]
    sep = g.n("ShaderNodeSeparateXYZ")
    g.l(uv, sep.inputs[0])
    u, v = sep.outputs["X"], sep.outputs["Y"]
    rnd = g.n("ShaderNodeObjectInfo").outputs["Random"]
    # long streaks along the ribbon: noise stretched along u
    sv = g.n("ShaderNodeCombineXYZ")
    g.l(g.math("MULTIPLY", u, 2.4), sv.inputs["X"])
    g.l(g.math("MULTIPLY", v, 9.0), sv.inputs["Y"])
    g.l(g.math("MULTIPLY", rnd, 37.0), sv.inputs["Z"])
    nz = g.n("ShaderNodeTexNoise", Scale=1.6, Detail=4.0, Roughness=0.55)
    g.l(sv.outputs[0], nz.inputs["Vector"])
    erode = g.value(0.42)
    streak = g.remap(nz.outputs["Factor"], 0.0, 1.0, 0.0, 1.0)
    streak = g.math("SUBTRACT", streak, erode.outputs[0])
    streak = g.math("MULTIPLY", streak, 4.0, clamp=True)
    head = g.math("POWER", u, 1.4)  # tail (u=0) fades, head (u=1) solid
    nose = g.remap(u, 0.86, 1.0, 1.0, 0.0)  # soft rounded nose
    edge = g.math("POWER", g.math("SINE", g.math("MULTIPLY", v, math.pi)), 0.8)
    alpha = g.math("MULTIPLY", g.math("MULTIPLY", streak, head), g.math("MULTIPLY", nose, edge), clamp=True)
    life = g.value(1.0)
    alpha = g.math("MULTIPLY", alpha, life.outputs[0], clamp=True)
    col = g.n("ShaderNodeRGB")
    col.outputs[0].default_value = (*tint, 1)
    g.emit_alpha(col.outputs[0], p.get("strength", 4.0), alpha)
    n = int(p.get("arcs", 8))
    rlo, rhi = p.get("radius", [0.35, 0.9])
    hlo, hhi = p.get("height", [-0.75, 0.75])
    slo, shi = p.get("span", [110, 230])
    wlo, whi = p.get("width", [0.04, 0.12])
    arcs = []
    seg = 64
    for i in range(n):
        r = rng.uniform(rlo, rhi)
        h = rng.uniform(hlo, hhi)
        span = math.radians(rng.uniform(slo, shi))
        w = rng.uniform(wlo, whi)
        rise = rng.uniform(-0.25, 0.25)
        verts, faces, uvs = [], [], []
        for s in range(seg + 1):
            t = s / seg
            a = span * t
            taper = math.sin(math.pi * min(1.0, t * 1.15)) ** 0.5
            x, y, z = math.cos(a), math.sin(a), rise * t
            hw = w * (0.35 + 0.65 * taper) / 2
            verts += [(x, y, z - hw / max(r, 0.2)), (x, y, z + hw / max(r, 0.2))]
            uvs += [(t, 0.0), (t, 1.0)]
            if s:
                b = 2 * s
                faces.append((b - 2, b, b + 1, b - 1))
        ob = mesh_object(sc, "Arc", verts, faces, uvs)
        ob.data.materials.append(g.mat)
        ob.rotation_euler = (math.radians(rng.uniform(-14, 14)), math.radians(rng.uniform(-14, 14)), 0)
        arcs.append((ob, r, h, rng.uniform(0, 2 * math.pi), rng.uniform(0.75, 1.3)))
    spin = math.radians(p.get("spin", 320))
    expand = p.get("expand", 0.7)

    def update(k):
        e = ease_out(k, 2.4)
        for ob, r, h, phase, speed in arcs:
            rr = r * (0.55 + expand * e)
            ob.scale = (rr, rr, 1.0)
            ob.location = (0, 0, h * (0.7 + 0.5 * e))
            ob.rotation_euler[2] = phase + spin * speed * e
        erode.outputs[0].default_value = 0.28 + 0.26 * smooth(0.45, 1.0, k)
        life.outputs[0].default_value = (0.35 + 0.65 * smooth(0.0, 0.08, k)) * (1 - smooth(0.8, 1.0, k) * 0.85)

    return update


def recipe_dust(sc, p, rng):
    """a billow of dust: lumpy lit volumes that burst out, rise and thin out (Cycles volumes, lit by the scene).
    params: puffs 7, spread 0.55, rise 0.35, density 9, key [r, g, b] (key light colour), flat 0.6 (y squash)"""
    camera(sc, ortho=p.get("frame", 2.4), loc=(0, -6, 0.15), look=(0, 0, 0.15))
    key = p.get("key", [1.0, 0.9, 0.75])
    sun(sc, 4.5, (40, -35, 25), key)
    sun(sc, 0.9, (110, 40, -140), (0.75, 0.82, 1.0))
    sc.world.node_tree.nodes["Background"].inputs[1].default_value = 0.35
    g = Graph("Dust")
    obj = g.n("ShaderNodeTexCoord").outputs["Object"]
    w = g.value(0.0)
    rnd = g.n("ShaderNodeObjectInfo").outputs["Random"]
    scaled = g.n("ShaderNodeVectorMath", operation="SCALE")
    g.l(obj, scaled.inputs[0])
    scaled.inputs["Scale"].default_value = 1.5
    nz = g.n("ShaderNodeTexNoise", Scale=1.3, Detail=6.0, Roughness=0.6, noise_dimensions="4D")
    g.l(scaled.outputs[0], nz.inputs["Vector"])
    g.l(g.math("ADD", w.outputs[0], g.math("MULTIPLY", rnd, 13.0)), nz.inputs["W"])
    ln = g.n("ShaderNodeVectorMath", operation="LENGTH")
    g.l(obj, ln.inputs[0])
    shape = g.math("ADD", g.math("MULTIPLY", nz.outputs["Factor"], 1.5), g.math("MULTIPLY", ln.outputs["Value"], -1.25))
    shape = g.math("SUBTRACT", shape, 0.1, clamp=True)
    dens_k = g.value(1.0)
    dens = g.math("MULTIPLY", g.math("MULTIPLY", shape, p.get("density", 9.0)), dens_k.outputs[0])
    vol = g.n("ShaderNodeVolumePrincipled", Anisotropy=0.25)
    vol.inputs["Color"].default_value = (0.92, 0.9, 0.86, 1)
    g.l(dens, vol.inputs["Density"])
    g.l(vol.outputs[0], g.out.inputs["Volume"])
    n = int(p.get("puffs", 7))
    spread = p.get("spread", 0.55)
    flat = p.get("flat", 0.6)
    puffs = []
    for i in range(n):
        bpy.ops.mesh.primitive_ico_sphere_add(radius=1.0, subdivisions=2)
        ob = bpy.context.active_object
        ob.data.materials.append(g.mat)
        a = rng.uniform(0, 2 * math.pi)
        d = spread * math.sqrt(rng.uniform(0.05, 1))
        base = (d * math.cos(a), d * math.sin(a) * flat, rng.uniform(-0.25, 0.1))
        slo, shi = p.get("size", [0.32, 0.55])
        puffs.append((ob, base, rng.uniform(slo, shi), rng.uniform(0.6, 1.2)))
    rise = p.get("rise", 0.35)

    def update(k):
        e = ease_out(k, 2.6)
        for ob, base, size, rs in puffs:
            s = size * (0.35 + 0.75 * e)
            ob.scale = (s, s * 0.95, s)
            ob.location = (base[0] * (0.6 + 0.6 * e), base[1], base[2] + rise * rs * e)
        w.outputs[0].default_value = k * 1.3
        dens_k.outputs[0].default_value = (1 - smooth(0.45, 1.0, k)) * smooth(0.0, 0.05, k + 0.02)

    return update


def recipe_flow(sc, p, rng):
    """a seamless energy-flow strip for Roblox Beams (wraps along its length; scroll it with TextureSpeed).
    The noise is sampled on a circle along u, so the right edge continues into the left with no seam.
    params: aspect 4 (width / height), stretch 0.9 (lower = longer streaks), fine 1.8, core 0.07 (bright line
    width), band 0.26 (body width), contrast 0 (0 soft haze .. 1 hard streaks with dark gaps), strength 6,
    gold [r, g, b], hot [r, g, b]"""
    aspect = p.get("aspect", 4)
    camera(sc, ortho=2.0, loc=(0, -5, 0))
    sc.render.resolution_y = int(sc.render.resolution_x / aspect)
    verts = [(-1, 0, -1 / aspect), (1, 0, -1 / aspect), (1, 0, 1 / aspect), (-1, 0, 1 / aspect)]
    ob = mesh_object(sc, "Strip", verts, [(0, 1, 2, 3)], [(0, 0), (1, 0), (1, 1), (0, 1)])
    g = Graph("Flow")
    uv = g.n("ShaderNodeUVMap").outputs["UV"]
    sep = g.n("ShaderNodeSeparateXYZ")
    g.l(uv, sep.inputs[0])
    u, v = sep.outputs["X"], sep.outputs["Y"]
    th = g.math("MULTIPLY", u, 2 * math.pi)
    seed = p.get("seed_w", rng.uniform(0, 50))

    def ring_noise(rad, vscale, scale, detail, w):
        c = g.n("ShaderNodeCombineXYZ")
        g.l(g.math("MULTIPLY", g.math("COSINE", th), rad), c.inputs["X"])
        g.l(g.math("MULTIPLY", g.math("SINE", th), rad), c.inputs["Y"])
        g.l(g.math("MULTIPLY", v, vscale), c.inputs["Z"])
        nz = g.n("ShaderNodeTexNoise", Scale=scale, Detail=detail, Roughness=0.55, noise_dimensions="4D")
        nz.inputs["W"].default_value = w
        g.l(c.outputs[0], nz.inputs["Vector"])
        return nz.outputs["Factor"]

    # contrast: how hard the streaks are cut out of the glow (0 = soft haze, 1 = racing streaks with dark gaps)
    ct = p.get("contrast", 0.0)
    coarse = g.remap(ring_noise(p.get("stretch", 0.9), 5.0, 1.0, 3.0, seed), 0.38 + 0.1 * ct, 0.72 - 0.1 * ct)
    fine = g.remap(ring_noise(p.get("fine", 1.8), 16.0, 1.0, 5.0, seed + 9), 0.42 + 0.1 * ct, 0.75 - 0.11 * ct)
    dv = g.math("SUBTRACT", v, 0.5)
    sq = g.math("MULTIPLY", dv, dv)
    bw, cw = p.get("band", 0.26), p.get("core", 0.07)
    band = g.math("EXPONENT", g.math("MULTIPLY", sq, -1.0 / (bw * bw)))
    core = g.math("EXPONENT", g.math("MULTIPLY", sq, -1.0 / (cw * cw)))
    edge = g.math("SINE", g.math("MULTIPLY", v, math.pi))
    body = g.math("MULTIPLY", band, g.math("ADD", g.math("MULTIPLY", coarse, 0.75 - 0.4 * ct), g.math("MULTIPLY", g.math("MULTIPLY", fine, coarse), 0.55 + 1.1 * ct)))
    inten = g.math("MULTIPLY", g.math("ADD", body, g.math("MULTIPLY", core, 1.6)), edge)
    gold, hot = p.get("gold", [1.0, 0.68, 0.2]), p.get("hot", [1.0, 0.97, 0.88])
    col = g.ramp(g.math("MULTIPLY", inten, 0.7), [(0.0, tuple(gold)), (0.55, (1.0, 0.86, 0.5)), (1.0, tuple(hot))])
    g.emit_alpha(col, g.math("MULTIPLY", inten, p.get("strength", 6.0)), 1.0)
    ob.data.materials.append(g.mat)
    return lambda k: None


def recipe_crack(sc, p, rng):
    """a glowing fissure torn into the ground, seen from above (a decal: lay it flat on the floor).
    A jagged main tear runs along x (two noise scales), its width breathing; short cracks branch off it
    (voronoi edges on noise-warped coordinates, kept only near the tear and broken into pieces); scorch around.
    params: wobble 0.07, core 0.03, cracks 5 (branch cell scale), reach 0.16, warp 0.18, glow [r, g, b], strength 8"""
    camera(sc, ortho=2.0, loc=(0, -5, 0))
    ob = mesh_object(sc, "Ground", [(-1, 0, -1), (1, 0, -1), (1, 0, 1), (-1, 0, 1)], [(0, 1, 2, 3)], [(0, 0), (1, 0), (1, 1), (0, 1)])
    g = Graph("Crack")
    obj = g.n("ShaderNodeTexCoord").outputs["Object"]
    sep = g.n("ShaderNodeSeparateXYZ")
    g.l(obj, sep.inputs[0])
    x, y = sep.outputs["X"], sep.outputs["Z"]
    seed = rng.uniform(0, 40)

    def noise1(scale, detail, w):
        c = g.n("ShaderNodeCombineXYZ")
        g.l(x, c.inputs["X"])
        c.inputs["Y"].default_value = w
        nz = g.n("ShaderNodeTexNoise", Scale=scale, Detail=detail, Roughness=0.6)
        g.l(c.outputs[0], nz.inputs["Vector"])
        return g.math("SUBTRACT", nz.outputs["Factor"], 0.5)

    wob = p.get("wobble", 0.07)
    y0 = g.math("ADD", g.math("MULTIPLY", noise1(1.1, 2.0, seed), wob * 4), g.math("MULTIPLY", noise1(6.0, 3.0, seed + 3), wob * 0.9))
    d = g.math("ABSOLUTE", g.math("SUBTRACT", y, y0))
    breathe = g.math("ADD", 0.55, g.math("MULTIPLY", g.math("ADD", noise1(2.5, 2.0, seed + 7), 0.5), 0.9))
    cw = g.math("MULTIPLY", breathe, p.get("core", 0.03))
    q = g.math("DIVIDE", d, cw)
    core = g.math("EXPONENT", g.math("MULTIPLY", g.math("MULTIPLY", q, q), -1.0))
    # branch cracks: voronoi edges on warped coordinates, near the tear only, broken into pieces
    warp = g.n("ShaderNodeTexNoise", Scale=2.2, Detail=3.0)
    g.l(obj, warp.inputs["Vector"])
    off = g.n("ShaderNodeVectorMath", operation="SUBTRACT")
    g.l(warp.outputs["Color"], off.inputs[0])
    off.inputs[1].default_value = (0.5, 0.5, 0.5)
    sc_off = g.n("ShaderNodeVectorMath", operation="SCALE")
    g.l(off.outputs[0], sc_off.inputs[0])
    sc_off.inputs["Scale"].default_value = p.get("warp", 0.18)
    wco = g.n("ShaderNodeVectorMath", operation="ADD")
    g.l(obj, wco.inputs[0])
    g.l(sc_off.outputs[0], wco.inputs[1])
    vor = g.n("ShaderNodeTexVoronoi", feature="DISTANCE_TO_EDGE", Scale=p.get("cracks", 5.0))
    vor.inputs["Randomness"].default_value = 1.0
    g.l(wco.outputs[0], vor.inputs["Vector"])
    line = g.remap(vor.outputs["Distance"], 0.0, 0.022, 1.0, 0.0)
    reach = p.get("reach", 0.16)
    near = g.math("EXPONENT", g.math("MULTIPLY", g.math("MULTIPLY", d, d), -1.0 / (reach * reach)))
    pieces = g.n("ShaderNodeTexNoise", Scale=3.5, Detail=2.0)
    g.l(obj, pieces.inputs["Vector"])
    keep = g.remap(pieces.outputs["Factor"], 0.45, 0.6)
    branch = g.math("MULTIPLY", g.math("MULTIPLY", line, g.math("POWER", near, 1.3)), keep)
    ends = g.remap(g.math("ABSOLUTE", x), 0.72, 0.97, 1.0, 0.0)
    glow = g.math("MULTIPLY", g.math("MAXIMUM", core, g.math("MULTIPLY", branch, 0.8)), ends, clamp=True)
    scorch_n = g.n("ShaderNodeTexNoise", Scale=4.0, Detail=6.0)
    g.l(obj, scorch_n.inputs["Vector"])
    sw = reach * 1.9
    scorch = g.math("EXPONENT", g.math("MULTIPLY", g.math("MULTIPLY", d, d), -1.0 / (sw * sw)))
    scorch = g.math("MULTIPLY", g.math("MULTIPLY", scorch, g.remap(scorch_n.outputs["Factor"], 0.3, 0.7, 0.4, 1.0)), ends)
    alpha = g.math("MAXIMUM", g.math("MULTIPLY", scorch, 0.9), glow)
    gc = p.get("glow", [1.0, 0.62, 0.2])
    col = g.ramp(glow, [(0.0, (0.03, 0.022, 0.018)), (0.2, tuple(c * 0.5 for c in gc)), (0.6, tuple(gc)), (1.0, (1.0, 0.95, 0.8))])
    strength = g.math("ADD", 1.0, g.math("MULTIPLY", glow, p.get("strength", 8.0)))
    g.emit_alpha(col, strength, alpha)
    ob.data.materials.append(g.mat)
    return lambda k: None


def recipe_blast(sc, p, rng):
    """an explosion of LIGHT (or fire): an emissive volume that bursts out, its hot core white, edges gold, amber,
    breaking into lumpy tongues as it expands and burns out (Cycles volume emission).
    params: lumps 1.6 (noise scale), grow [0.25, 1.0] (radius over the sheet), heat 26 (emission at the core),
    smoke 0.0 (dark absorbing smoke that remains at the end: 0..1), core [r,g,b], mid [r,g,b], rim [r,g,b]"""
    camera(sc, ortho=p.get("frame", 2.3), loc=(0, -6, 0))
    bpy.ops.mesh.primitive_ico_sphere_add(radius=1.0, subdivisions=3)
    ob = bpy.context.active_object
    g = Graph("Blast")
    obj = g.n("ShaderNodeTexCoord").outputs["Object"]
    w = g.value(0.0)
    nz = g.n("ShaderNodeTexNoise", Scale=p.get("lumps", 1.6), Detail=6.0, Roughness=0.62, noise_dimensions="4D")
    g.l(obj, nz.inputs["Vector"])
    g.l(w.outputs[0], nz.inputs["W"])
    ln = g.n("ShaderNodeVectorMath", operation="LENGTH")
    g.l(obj, ln.inputs[0])
    edge = g.value(0.0)  # rises over the sheet: the volume burns away from the outside in
    shape = g.math("ADD", g.math("MULTIPLY", nz.outputs["Factor"], p.get("tongues", 1.7)), g.math("MULTIPLY", ln.outputs["Value"], -1.2))
    shape = g.math("SUBTRACT", shape, g.math("ADD", edge.outputs[0], (p.get("tongues", 1.7) - 1.35) * 0.5))
    body = g.math("MULTIPLY", shape, 3.0, clamp=True)
    # temperature: deep inside (low radius, high noise) = white, then gold, amber at the rim
    temp = g.math("MULTIPLY", g.math("SUBTRACT", 1.15, ln.outputs["Value"]), body, clamp=True)
    col = g.ramp(temp, [(0.0, tuple(p.get("rim", [1.0, 0.42, 0.08]))), (0.4, tuple(p.get("mid", [1.0, 0.72, 0.25]))), (0.8, tuple(p.get("core", [1.0, 0.95, 0.82]))), (1.0, (1, 1, 1))])
    heat = g.value(1.0)
    strength = g.math("MULTIPLY", g.math("MULTIPLY", g.math("POWER", temp, 1.5), p.get("heat", 26.0)), heat.outputs[0])
    smoke = g.value(0.0)
    vol = g.n("ShaderNodeVolumePrincipled")
    vol.inputs["Color"].default_value = (0.08, 0.07, 0.065, 1)
    g.l(g.math("MULTIPLY", body, g.math("ADD", 0.15, g.math("MULTIPLY", smoke.outputs[0], 6.0))), vol.inputs["Density"])
    g.l(col, vol.inputs["Emission Color"])
    g.l(strength, vol.inputs["Emission Strength"])
    g.l(vol.outputs[0], g.out.inputs["Volume"])
    ob.data.materials.append(g.mat)
    lo, hi = p.get("grow", [0.25, 1.0])
    smoke_end = p.get("smoke", 0.0)

    def update(k):
        e = ease_out(k, 2.8)
        s = lo + (hi - lo) * e
        ob.scale = (s, s, s)
        w.outputs[0].default_value = k * 1.6 + rng.random() * 0
        edge.outputs[0].default_value = -0.15 + 0.5 * smooth(0.25, 1.0, k)
        heat.outputs[0].default_value = (1 - smooth(0.05, 0.95, k)) ** 1.4 + 0.02
        smoke.outputs[0].default_value = smoke_end * smooth(0.3, 0.9, k)

    return update


def recipe_ring(sc, p, rng):
    """a shockwave ring seen from above: a bright leading edge, a soft trailing wash inside it, the edge torn by
    noise, expanding and thinning as it goes (use it flat: VelocityPerpendicular sprites or a ground decal).
    params: grow [0.25, 0.95] (radius over the sheet), edge 0.05 (leading edge width), wash 0.22 (inner trail),
    tear 0.6 (0..1 how much noise breaks the edge), strength 7, rim [r, g, b], body [r, g, b]"""
    camera(sc, ortho=2.0, loc=(0, -5, 0))
    ob = mesh_object(sc, "Plate", [(-1, 0, -1), (1, 0, -1), (1, 0, 1), (-1, 0, 1)], [(0, 1, 2, 3)], [(0, 0), (1, 0), (1, 1), (0, 1)])
    g = Graph("Ring")
    obj = g.n("ShaderNodeTexCoord").outputs["Object"]
    sep = g.n("ShaderNodeSeparateXYZ")
    g.l(obj, sep.inputs[0])
    ln = g.n("ShaderNodeVectorMath", operation="LENGTH")
    g.l(obj, ln.inputs[0])
    r = ln.outputs["Value"]
    radius = g.value(0.5)
    edge_w = g.value(p.get("edge", 0.05))
    wash_w = p.get("wash", 0.22)
    d = g.math("SUBTRACT", r, radius.outputs[0])  # > 0 outside the ring, < 0 inside
    # tear: angular noise (sampled on the unit circle -> seamless) breaks the edge into pieces
    nrm = g.n("ShaderNodeVectorMath", operation="NORMALIZE")
    g.l(obj, nrm.inputs[0])
    sc_v = g.n("ShaderNodeVectorMath", operation="SCALE")
    g.l(nrm.outputs[0], sc_v.inputs[0])
    sc_v.inputs["Scale"].default_value = 2.2
    w = g.value(rng.uniform(0, 30))
    nz = g.n("ShaderNodeTexNoise", Scale=1.6, Detail=5.0, Roughness=0.6, noise_dimensions="4D")
    g.l(sc_v.outputs[0], nz.inputs["Vector"])
    g.l(w.outputs[0], nz.inputs["W"])
    tear = g.remap(nz.outputs["Factor"], 0.35, 0.65, 1 - p.get("tear", 0.6), 1.0)
    q = g.math("DIVIDE", d, edge_w.outputs[0])
    rim = g.math("EXPONENT", g.math("MULTIPLY", g.math("MULTIPLY", q, q), -1.0))
    inside = g.math("LESS_THAN", d, 0.0)
    wash = g.math("MULTIPLY", inside, g.math("EXPONENT", g.math("DIVIDE", d, wash_w)))
    life = g.value(1.0)
    inten = g.math("MULTIPLY", g.math("ADD", g.math("MULTIPLY", rim, tear), g.math("MULTIPLY", wash, g.math("MULTIPLY", tear, 0.35))), life.outputs[0])
    col = g.ramp(inten, [(0.0, tuple(p.get("body", [1.0, 0.62, 0.2]))), (0.6, (1.0, 0.86, 0.55)), (1.0, tuple(p.get("rim", [1.0, 0.97, 0.9])))])
    g.emit_alpha(col, g.math("MULTIPLY", inten, p.get("strength", 7.0)), 1.0)
    ob.data.materials.append(g.mat)
    lo, hi = p.get("grow", [0.25, 0.95])
    base_edge = p.get("edge", 0.05)

    def update(k):
        radius.outputs[0].default_value = lo + (hi - lo) * ease_out(k, 2.5)
        edge_w.outputs[0].default_value = base_edge * (1.0 - 0.6 * k) + 0.004
        w.outputs[0].default_value += 0.06
        life.outputs[0].default_value = (1 - smooth(0.45, 1.0, k)) * smooth(0.0, 0.05, k + 0.03)

    return update


def recipe_wave(sc, p, rng):
    """a crescent WAVE of light seen face-on (the slash wave that flies ahead of a beam, a sword's arc): a thick
    bright crescent whose inner edge is sharp and whose outer edge trails into streaks, torn by noise, with a white
    core line. Frames: the crescent thickens then thins and frays (one-shot).
    params: radius 0.62, arc 150 (degrees), thick [0.06, 0.2] (over the sheet), trail 0.25 (streak length behind),
    tear 0.5, strength 7, rim [r,g,b], mid [r,g,b] (the middle stop: gold unless set), body [r,g,b]"""
    camera(sc, ortho=2.0, loc=(0, -5, 0))
    ob = mesh_object(sc, "Plate", [(-1, 0, -1), (1, 0, -1), (1, 0, 1), (-1, 0, 1)], [(0, 1, 2, 3)], [(0, 0), (1, 0), (1, 1), (0, 1)])
    g = Graph("Wave")
    obj = g.n("ShaderNodeTexCoord").outputs["Object"]
    sep = g.n("ShaderNodeSeparateXYZ")
    g.l(obj, sep.inputs[0])
    x, y = sep.outputs["X"], sep.outputs["Z"]
    ln = g.n("ShaderNodeVectorMath", operation="LENGTH")
    g.l(obj, ln.inputs[0])
    r = ln.outputs["Value"]
    ang = g.math("ARCTAN2", x, y)  # 0 = +y (the crescent's tip points up the sheet)
    half = math.radians(p.get("arc", 150) / 2)
    along = g.math("DIVIDE", g.math("ABSOLUTE", ang), half)  # 0 at the middle, 1 at the tips
    tipfade = g.remap(along, 0.55, 1.0, 1.0, 0.0)
    radius = p.get("radius", 0.62)
    thick = g.value(0.1)
    d = g.math("SUBTRACT", r, radius)  # >0 outside (ahead), <0 inside (behind)
    # leading edge: sharp; trailing side: exponential streak tail
    front = g.remap(d, 0.0, 0.015, 1.0, 0.0)
    back = g.math("EXPONENT", g.math("DIVIDE", d, g.math("MULTIPLY", thick.outputs[0], 1.0)))
    body = g.math("MINIMUM", front, g.math("MULTIPLY", g.math("LESS_THAN", d, 0.0), back))
    # streaks along the radius behind the crescent (angular noise, radial stretch)
    c = g.n("ShaderNodeCombineXYZ")
    g.l(g.math("MULTIPLY", ang, 14.0), c.inputs["X"])
    g.l(g.math("MULTIPLY", r, 3.0), c.inputs["Y"])
    w = g.value(rng.uniform(0, 30))
    nz = g.n("ShaderNodeTexNoise", Scale=1.0, Detail=4.0, Roughness=0.55, noise_dimensions="4D")
    g.l(c.outputs[0], nz.inputs["Vector"])
    g.l(w.outputs[0], nz.inputs["W"])
    tear = g.remap(nz.outputs["Factor"], 0.3, 0.7, 1 - p.get("tear", 0.5), 1.0)
    trail = g.math("MULTIPLY", g.math("LESS_THAN", d, 0.0), g.math("EXPONENT", g.math("DIVIDE", d, p.get("trail", 0.25))))
    trail = g.math("MULTIPLY", trail, g.remap(nz.outputs["Factor"], 0.45, 0.75))
    core = g.math("EXPONENT", g.math("MULTIPLY", g.math("MULTIPLY", d, d), -1.0 / (0.012 * 0.012)))
    life = g.value(1.0)
    inten = g.math("MULTIPLY", g.math("ADD", g.math("MULTIPLY", g.math("ADD", body, g.math("MULTIPLY", trail, 0.6)), tear), g.math("MULTIPLY", core, 1.2)), tipfade)
    inten = g.math("MULTIPLY", inten, life.outputs[0])
    col = g.ramp(inten, [(0.0, tuple(p.get("body", [1.0, 0.6, 0.18]))), (0.55, tuple(p.get("mid", [1.0, 0.84, 0.5]))), (1.0, tuple(p.get("rim", [1.0, 0.98, 0.92])))])
    g.emit_alpha(col, g.math("MULTIPLY", inten, p.get("strength", 7.0)), 1.0)
    ob.data.materials.append(g.mat)
    tlo, thi = p.get("thick", [0.06, 0.2])

    def update(k):
        thick.outputs[0].default_value = tlo + (thi - tlo) * math.sin(math.pi * min(1.0, k * 1.2)) + 0.003
        w.outputs[0].default_value += 0.08
        life.outputs[0].default_value = smooth(0.0, 0.08, k + 0.04) * (1 - smooth(0.55, 1.0, k))

    return update


def recipe_rays(sc, p, rng):
    """god rays: a fan of light rays from a point at the bottom centre, each ray a long soft streak with its own
    length and brightness, flickering frame to frame (use upright above an impact, or rotated as a sun burst).
    params: rays 26, spread 70 (degrees total), length [0.5, 1.0], width 0.012, strength 6, flicker 0.5,
    color [r,g,b]"""
    camera(sc, ortho=2.0, loc=(0, -5, 0))
    ob = mesh_object(sc, "Plate", [(-1, 0, -1), (1, 0, -1), (1, 0, 1), (-1, 0, 1)], [(0, 1, 2, 3)], [(0, 0), (1, 0), (1, 1), (0, 1)])
    g = Graph("Rays")
    obj = g.n("ShaderNodeTexCoord").outputs["Object"]
    sep = g.n("ShaderNodeSeparateXYZ")
    g.l(obj, sep.inputs[0])
    x = sep.outputs["X"]
    yy = g.math("ADD", sep.outputs["Z"], p.get("origin", 0.95))  # origin 0.95 = near the bottom edge; lower = inside the cell (no cut)
    r = g.math("SQRT", g.math("ADD", g.math("MULTIPLY", x, x), g.math("MULTIPLY", yy, yy)))
    ang = g.math("ARCTAN2", x, yy)
    n = int(p.get("rays", 26))
    spread = math.radians(p.get("spread", 70))
    width = p.get("width", 0.012)
    llo, lhi = p.get("length", [0.5, 1.0])
    total = None
    knobs = []
    for i in range(n):
        a = (i / max(1, n - 1) - 0.5) * spread + rng.uniform(-0.5, 0.5) * spread / n
        length = rng.uniform(llo, lhi) * 1.9
        da = g.math("SUBTRACT", ang, a)
        across = g.math("EXPONENT", g.math("MULTIPLY", g.math("MULTIPLY", da, da), -1.0 / (width * width)))
        along = g.math("MULTIPLY", g.math("EXPONENT", g.math("DIVIDE", r, -length * 0.55)), g.remap(r, 0.0, 0.08))
        bright = g.value(rng.uniform(0.4, 1.0))
        knobs.append((bright, rng.uniform(0, 6.28), rng.uniform(0.5, 1.5)))
        ray = g.math("MULTIPLY", g.math("MULTIPLY", across, along), bright.outputs[0])
        total = ray if total is None else g.math("ADD", total, ray)
    glow = g.math("EXPONENT", g.math("DIVIDE", r, -0.25))
    above = g.remap(yy, -0.01 - p.get("below", 0.0), 0.1, 0.0, 1.0)  # the fan starts AT the origin (below: a soft tail under it)
    edge = g.remap(r, 0.72 * p.get("reach", 1.0), 0.96 * p.get("reach", 1.0), 1.0, 0.0)  # nothing reaches the cell's edge
    inten = g.math("MULTIPLY", g.math("MULTIPLY", g.math("ADD", total, g.math("MULTIPLY", glow, 0.5)), edge), above)
    col_rgb = p.get("color", [1.0, 0.86, 0.55])
    col = g.ramp(g.math("MULTIPLY", inten, 0.8), [(0.0, tuple(c * 0.9 for c in col_rgb)), (1.0, (1.0, 0.98, 0.92))])
    g.emit_alpha(col, g.math("MULTIPLY", inten, p.get("strength", 6.0)), 1.0)
    ob.data.materials.append(g.mat)
    flicker = p.get("flicker", 0.5)

    def update(k):
        for bright, phase, speed in knobs:
            bright.outputs[0].default_value = max(0.05, (0.7 + 0.3 * math.sin(phase + k * speed * 12)) * (1 - flicker * 0.5 * (0.5 + 0.5 * math.sin(phase * 2 + k * speed * 25))))

    return update


def _ribbon(sc, name, mat):
    """an empty ribbon mesh whose vertices update(k) rewrites: _ribbon_set(ob, points, widths)"""
    ob = mesh_object(sc, name, [(0, 0, 0), (0, 0, 0.001), (0.001, 0, 0.001), (0.001, 0, 0)], [(0, 1, 2, 3)], [(0, 0), (0, 1), (1, 1), (1, 0)])
    ob.data.materials.append(mat)
    return ob


def _ribbon_set(ob, pts, widths):
    """rebuild a flat ribbon (in the camera plane y = 0) along pts [(x, z)] with a width per point; UV u = across"""
    me = ob.data
    verts, faces, uvs = [], [], []
    n = len(pts)
    for i, (x, z) in enumerate(pts):
        ax, az = pts[min(i + 1, n - 1)][0] - pts[max(i - 1, 0)][0], pts[min(i + 1, n - 1)][1] - pts[max(i - 1, 0)][1]
        L = math.hypot(ax, az) or 1.0
        nx, nz = -az / L * widths[i] / 2, ax / L * widths[i] / 2
        verts.append((x - nx, 0.0, z - nz))
        verts.append((x + nx, 0.0, z + nz))
        uvs.append((0.0, i / max(1, n - 1)))
        uvs.append((1.0, i / max(1, n - 1)))
        if i > 0:
            a = 2 * (i - 1)
            faces.append((a, a + 1, a + 3, a + 2))
    new = bpy.data.meshes.new(me.name + "_r")
    new.from_pydata(verts, [], faces)
    layer = new.uv_layers.new(name="UVMap")
    for poly in new.polygons:
        for li, vi in zip(poly.loop_indices, poly.vertices):
            layer.data[li].uv = uvs[vi]
    for p in new.polygons:
        p.use_smooth = True
    for m in me.materials:
        new.materials.append(m)
    ob.data = new
    bpy.data.meshes.remove(me)


def _bolt_path(rng, x0, z0, x1, z1, segments, wobble):
    """a jagged path from (x0, z0) to (x1, z1): a random walk pulled back to the chord, finer wobble near the end"""
    pts = [(x0, z0)]
    for i in range(1, segments):
        t = i / segments
        cx, cz = x0 + (x1 - x0) * t, z0 + (z1 - z0) * t
        amp = wobble * math.sin(math.pi * t) ** 0.6
        px = cx + rng.gauss(0, amp)
        pz = cz + rng.gauss(0, amp * 0.4)
        pts.append((px, pz))
    pts.append((x1, z1))
    return pts


def recipe_lightning(sc, p, rng):
    """lightning seen face-on: a jagged main bolt from the top down (random walk around the chord, finer near the
    tip) with thinner branches forking off it, a white core inside a coloured glow (post.glow adds the bloom). Frames:
    `strikes` bolts in turn (a new path each), each one flashing in, flickering with its branches, snapping out.
    params: strikes 2, segments 22, wobble 0.22, width 0.045, branches 5, branch_len [0.25, 0.6], color [r,g,b]
    (the glow), strength 9, flicker 0.6, from [x, z] top, to [x, z] bottom (keep |z| <= 0.85: the glow needs the margin)"""
    camera(sc, ortho=2.0, loc=(0, -5, 0))
    g = Graph("Bolt")
    uv = g.n("ShaderNodeTexCoord").outputs["UV"]
    sep = g.n("ShaderNodeSeparateXYZ")
    g.l(uv, sep.inputs[0])
    across = g.math("ABSOLUTE", g.math("SUBTRACT", g.math("MULTIPLY", sep.outputs["X"], 2.0), 1.0))  # 0 core, 1 edge
    core = g.math("POWER", g.math("SUBTRACT", 1.0, across, clamp=True), 2.2)
    bright = g.value(1.0)
    col_rgb = tuple(p.get("color", [0.55, 0.7, 1.0]))
    col = g.ramp(core, [(0.0, col_rgb), (0.6, (0.85, 0.92, 1.0)), (1.0, (1, 1, 1))])
    g.emit_alpha(col, g.math("MULTIPLY", g.math("MULTIPLY", core, p.get("strength", 9.0)), bright.outputs[0]), 1.0)
    strikes = max(1, int(p.get("strikes", 2)))
    segments = int(p.get("segments", 22))
    wobble = p.get("wobble", 0.22)
    width = p.get("width", 0.045)
    nb = int(p.get("branches", 5))
    blo, bhi = p.get("branch_len", [0.25, 0.6])
    fx, fz = p.get("from", [0.0, 0.82])
    tx, tz = p.get("to", [0.0, -0.82])
    bolts = []
    for s in range(strikes):
        main = _bolt_path(rng, fx + rng.uniform(-0.15, 0.15), fz, tx + rng.uniform(-0.25, 0.25), tz, segments, wobble)
        branches = []
        for _ in range(nb):
            i = rng.randrange(2, len(main) - 3)
            bx, bz = main[i]
            L = rng.uniform(blo, bhi)
            ang = math.atan2(main[i + 1][1] - main[i - 1][1], main[i + 1][0] - main[i - 1][0]) + rng.choice((-1, 1)) * rng.uniform(0.5, 1.1)
            branches.append((_bolt_path(rng, bx, bz, bx + math.cos(ang) * L, bz + math.sin(ang) * L, max(4, segments // 3), wobble * 0.5), rng.uniform(0.3, 0.7), rng.uniform(0, 6.28)))
        bolts.append((main, branches))
    ribbons = [[_ribbon(sc, f"Bolt{s}", g.mat)] + [_ribbon(sc, f"Branch{s}_{j}", g.mat) for j in range(nb)] for s in range(strikes)]
    flicker = p.get("flicker", 0.6)

    def update(k):
        win = 1.0 / strikes
        s = min(strikes - 1, int(k / win))
        u = (k - s * win) / win  # 0..1 inside this strike
        env = smooth(0.0, 0.12, u) * (1 - smooth(0.6, 1.0, u))
        bright.outputs[0].default_value = env * (1 - flicker * 0.5 * (0.5 + 0.5 * math.sin(u * 40 + s)))
        for si, (main, branches) in enumerate(bolts):
            objs = ribbons[si]
            if si != s:
                for ob in objs:
                    ob.hide_render = True
                continue
            jitter = [(x + rng.gauss(0, 0.006), z + rng.gauss(0, 0.006)) if 0 < i < len(main) - 1 else (x, z) for i, (x, z) in enumerate(main)]
            n = len(jitter)
            widths = [width * (1.0 - 0.6 * (i / (n - 1))) * (0.7 + 0.3 * env) for i in range(n)]
            objs[0].hide_render = False
            _ribbon_set(objs[0], jitter, widths)
            for j, (path, bb, phase) in enumerate(branches):
                ob = objs[j + 1]
                on = u > 0.1 + j * 0.04 and (0.5 + 0.5 * math.sin(phase + u * 30)) > 0.35
                ob.hide_render = not on
                if on:
                    m = len(path)
                    _ribbon_set(ob, path, [width * bb * (1.0 - 0.8 * (i / (m - 1))) for i in range(m)])

    return update


def recipe_slash(sc, p, rng):
    """a sword's slash ARC seen face-on (anime cut): the band the blade sweeps, drawn in from the start angle to the
    end over the first part of the sheet — bright sharp leading edge, a white core line near the outer radius, the
    tail thinning and fraying into motion streaks along the arc, then the whole arc fades. `post.color: "cel"`
    turns it into flat anime bands.
    params: arc [-120, 120] (degrees, 0 = up), radius [0.45, 0.85] (inner, outer), taper 0.55 (how thin the tail
    gets), sweep 0.45 (fraction of the sheet the draw-in takes), streaks 0.5, strength 7, body [r,g,b], rim [r,g,b],
    core "outer" | "inner" (where the white-hot line runs: Flame Arc's fire crescent is white on its INNER edge),
    rag 0 (0..0.15: the outer edge torn by angular noise - a burning rim that breaks into tongues, not a clean arc),
    mid [1.0, 0.86, 0.55] (the ramp's middle colour), body_level 1.0 (the band's own brightness on the ramp: < 1 keeps a
    saturated body - only the core line and the leading edge climb to the rim colour), core_width 0.018 (the hot line's
    half-width: 0.05+ is the WIDE white-yellow band of FlameArc's arc), radial 0 (0..1: the body dims from the inner edge
    out, so the outer rim burns dark red - the scene's layers)"""
    camera(sc, ortho=2.0, loc=(0, -5, 0))
    ob = mesh_object(sc, "Plate", [(-1, 0, -1), (1, 0, -1), (1, 0, 1), (-1, 0, 1)], [(0, 1, 2, 3)], [(0, 0), (1, 0), (1, 1), (0, 1)])
    g = Graph("Slash")
    obj = g.n("ShaderNodeTexCoord").outputs["Object"]
    sep = g.n("ShaderNodeSeparateXYZ")
    g.l(obj, sep.inputs[0])
    x, y = sep.outputs["X"], sep.outputs["Z"]
    ln = g.n("ShaderNodeVectorMath", operation="LENGTH")
    g.l(obj, ln.inputs[0])
    r = ln.outputs["Value"]
    ang = g.math("ARCTAN2", x, y)
    a0, a1 = [math.radians(a) for a in p.get("arc", [-120, 120])]
    rin, rout = p.get("radius", [0.45, 0.85])
    along = g.remap(ang, a0, a1, clamp=False)  # 0 at the start of the swing, 1 at its end; outside the arc < 0 or > 1 (cut below)
    head = g.value(0.0)  # how far the arc has been drawn (0..1 along)
    drawn = g.remap(g.math("SUBTRACT", head.outputs[0], along), 0.0, 0.03)  # 1 behind the head, sharp front
    taper = p.get("taper", 0.55)
    # band: the outer radius holds, the inner radius rises towards the tail (thin at the start of the swing)
    inner = g.math("ADD", rin, g.math("MULTIPLY", g.math("SUBTRACT", 1.0, along), (rout - rin) * taper))
    rag = p.get("rag", 0.0)
    outer = rout
    if rag > 0:  # (2026-11-10) a torn outer edge: coarse angular noise moves the rim in and out
        c2 = g.n("ShaderNodeCombineXYZ")
        g.l(g.math("MULTIPLY", ang, 3.0), c2.inputs["X"])
        g.l(g.math("MULTIPLY", r, 4.0), c2.inputs["Y"])
        nz2 = g.n("ShaderNodeTexNoise", Scale=2.2, Detail=4.0, Roughness=0.6)
        g.l(c2.outputs[0], nz2.inputs["Vector"])
        outer = g.math("ADD", rout - rag * 0.5, g.math("MULTIPLY", nz2.outputs["Factor"], rag))
    band = g.math("MULTIPLY", g.math("DIVIDE", g.math("SUBTRACT", r, inner), 0.03, clamp=True),
                  g.remap(g.math("SUBTRACT", r, outer), -0.02, 0.0, 1.0, 0.0) if rag > 0 else g.remap(r, rout - 0.02, rout, 1.0, 0.0))
    chunks = p.get("chunks", 0.0)
    if chunks > 0:  # (2026-11-11) the outer share of the body breaks into separate flame islands - FlameArc's rim tears
        # into chunks of fire (the scene's key frame: 10 separate pieces; a smooth band read as 'a glowing donut'). A noise
        # threshold rises from 0 at (1 - chunks) of the band's width to full by (1 - 0.4 chunks): past it only the noise's
        # peaks survive, as islands with gaps all round (a ramp reaching full only AT the rim just scalloped the edge)
        across_c = g.math("DIVIDE", g.math("SUBTRACT", r, inner), max(rout - rin, 1e-3), clamp=True)
        cs = p.get("chunk_scale", 9.0)
        c3 = g.n("ShaderNodeCombineXYZ")
        g.l(g.math("MULTIPLY", ang, cs), c3.inputs["X"])
        g.l(g.math("MULTIPLY", r, cs * 2.0), c3.inputs["Y"])
        nz3 = g.n("ShaderNodeTexNoise", Scale=1.0, Detail=2.0, Roughness=0.5)
        g.l(c3.outputs[0], nz3.inputs["Vector"])
        thr = g.math("MULTIPLY", g.remap(across_c, 1.0 - chunks, 1.0 - 0.4 * chunks), p.get("chunk_cut", 0.62))
        band = g.math("MULTIPLY", band, g.remap(g.math("SUBTRACT", nz3.outputs["Factor"], thr), 0.0, 0.03))
    # streaks along the arc: noise stretched angularly
    c = g.n("ShaderNodeCombineXYZ")
    g.l(g.math("MULTIPLY", ang, 2.0), c.inputs["X"])
    g.l(g.math("MULTIPLY", r, 26.0), c.inputs["Y"])
    w = g.value(rng.uniform(0, 30))
    nz = g.n("ShaderNodeTexNoise", Scale=1.0, Detail=3.0, Roughness=0.5, noise_dimensions="4D")
    g.l(c.outputs[0], nz.inputs["Vector"])
    g.l(w.outputs[0], nz.inputs["W"])
    streak = g.remap(nz.outputs["Factor"], 0.35, 0.65, 1 - p.get("streaks", 0.5), 1.0)
    core_at = g.math("ADD", inner, 0.035) if p.get("core") == "inner" else rout - 0.06  # (inner: the hot line rides the inner edge)
    cw = p.get("core_width", 0.018)
    core = g.math("EXPONENT", g.math("MULTIPLY", g.math("MULTIPLY", g.math("SUBTRACT", r, core_at), g.math("SUBTRACT", r, core_at)), -1.0 / (cw * cw)))
    edge = g.math("EXPONENT", g.math("MULTIPLY", g.math("MULTIPLY", g.math("SUBTRACT", along, head.outputs[0]), g.math("SUBTRACT", along, head.outputs[0])), -1.0 / (0.02 * 0.02)))
    life = g.value(1.0)
    body_level = p.get("body_level", 1.0)
    radial = p.get("radial", 0.0)
    if radial > 0:  # (2026-11-11) the body dims from the inner edge outward: white-yellow inside, a dark-red burning rim
        across = g.math("DIVIDE", g.math("SUBTRACT", r, inner), max(rout - rin, 1e-3), clamp=True)
        body_level = g.math("MULTIPLY", body_level, g.math("SUBTRACT", 1.0, g.math("MULTIPLY", across, radial)))
    inten = g.math("MULTIPLY", g.math("ADD", g.math("MULTIPLY", g.math("MULTIPLY", g.math("MULTIPLY", band, streak), drawn), body_level), g.math("MULTIPLY", g.math("ADD", g.math("MULTIPLY", g.math("MULTIPLY", core, band), drawn), g.math("MULTIPLY", edge, band)), 1.3)), life.outputs[0])
    inten = g.math("MULTIPLY", inten, g.remap(along, -0.02, 0.0))
    inten = g.math("MULTIPLY", inten, g.remap(along, 1.0, 1.02, 1.0, 0.0))
    col = g.ramp(inten, [(0.0, tuple(p.get("body", [1.0, 0.62, 0.2]))), (0.5, tuple(p.get("mid", [1.0, 0.86, 0.55]))), (1.0, tuple(p.get("rim", [1.0, 0.98, 0.94])))])
    g.emit_alpha(col, g.math("MULTIPLY", inten, p.get("strength", 7.0)), 1.0)
    ob.data.materials.append(g.mat)
    sweep = p.get("sweep", 0.45)

    def update(k):
        head.outputs[0].default_value = min(1.05, ease_out(k / sweep, 2.2) * 1.05)
        w.outputs[0].default_value += 0.1
        life.outputs[0].default_value = max(0.0, 1 - (k - sweep - 0.1) / (0.9 - sweep))  # a straight fade: empty only on the last frame

    return update


def recipe_shards(sc, p, rng):
    """a burst of faceted crystal / glass / ice shards flying out from the centre, spinning, catching light on their
    facets (a facing-based rim so they read as hard and translucent without any environment), thinning and fading
    at the end. One-shot: scale it, tint it with the preset's colour.
    params: count 22, size [0.05, 0.18], depth 0.5 (how 3D the flight is), spin 2.5, tint [r,g,b], strength 5,
    hot 2 (facet highlight), reach 0.9 (how far they fly by the end)"""
    camera(sc, ortho=2.2, loc=(0, -6, 0))
    g = Graph("Shard")
    lw = g.n("ShaderNodeLayerWeight", Blend=0.4)
    facing = g.math("SUBTRACT", 1.0, lw.outputs["Facing"], clamp=True)
    rim = g.math("POWER", lw.outputs["Fresnel"], 1.5)
    tint = tuple(p.get("tint", [0.75, 0.9, 1.0]))
    fade = g.value(1.0)
    strength = g.math("MULTIPLY", g.math("ADD", g.math("MULTIPLY", g.math("POWER", facing, 3.0), p.get("hot", 2.0)), g.math("MULTIPLY", rim, 1.0)), p.get("strength", 5.0))
    strength = g.math("MULTIPLY", strength, fade.outputs[0])
    col = g.ramp(facing, [(0.0, tint), (0.7, (0.92, 0.97, 1.0)), (1.0, (1, 1, 1))])
    g.emit_alpha(col, strength, g.math("MULTIPLY", g.remap(rim, 0.0, 0.5, 0.55, 1.0), fade.outputs[0]))
    bm = bmesh.new()
    verts = [bm.verts.new(v) for v in [(0, 0, 1.0), (-0.35, 0, -0.2), (0.3, 0, -0.45), (0.05, 0.12, 0.1), (0.05, -0.12, 0.1)]]
    for tri in [(0, 1, 3), (0, 3, 2), (1, 2, 3), (0, 4, 1), (0, 2, 4), (1, 4, 2)]:
        try:
            bm.faces.new([verts[i] for i in tri])
        except ValueError:
            pass
    me = bpy.data.meshes.new("Shard")
    bm.to_mesh(me)
    bm.free()
    me.materials.append(g.mat)
    n = int(p.get("count", 22))
    slo, shi = p.get("size", [0.05, 0.18])
    depth = p.get("depth", 0.5)
    shards = []
    for _ in range(n):
        d = np.array([rng.gauss(0, 1), rng.gauss(0, 1) * depth, rng.gauss(0, 1)])
        d /= np.linalg.norm(d) + 1e-9
        ob = bpy.data.objects.new("Shard", me)
        sc.collection.objects.link(ob)
        ob.rotation_mode = "XYZ"
        s = rng.uniform(slo, shi)
        shards.append((ob, d, s, np.array([rng.uniform(0, 6.28) for _ in range(3)]), np.array([rng.gauss(0, 1) for _ in range(3)]) * p.get("spin", 2.5), rng.uniform(0.6, 1.0)))
    reach = p.get("reach", 0.9)

    def update(k):
        fade.outputs[0].default_value = smooth(0.0, 0.06, k + 0.02) * (1 - smooth(0.8, 1.0, k) ** 2)  # gone only on the last frame
        for ob, d, s, rot0, spin, speed in shards:
            dist = (0.06 + reach * ease_out(k * speed, 1.6)) * (0.8 + 0.2 * speed)
            ob.location = tuple(d * dist)
            ob.rotation_euler = tuple(rot0 + spin * k * 6.28)
            sz = s * (0.6 + 0.4 * ease_out(k * 4, 2)) * (1 - 0.5 * smooth(0.7, 1.0, k))
            ob.scale = (sz, sz, sz)

    return update


def recipe_cel(sc, p, rng):
    """an anime cel puff: a cluster of overlapping spheres (big in the middle, small at the rim) shaded by facing
    only — a bright face, a darker rim, no lights — so `post.color: "cel"` posterises it into flat bands with hard
    edges (the hand-drawn smoke / impact puff). Frames: the cluster swells and drifts up, the spheres shrink away.
    params: blobs 9, radius [0.12, 0.42], spread 0.55, rise 0.25, bands (set post.bands), tint [r,g,b], strength 1.2"""
    camera(sc, ortho=2.0, loc=(0, -5, 0))
    g = Graph("Cel")
    lw = g.n("ShaderNodeLayerWeight", Blend=0.55)
    face = g.math("SUBTRACT", 1.0, lw.outputs["Facing"], clamp=True)
    # a key-light direction baked as a dot product with the normal (up-left), so the bands sit like a drawn puff
    nrm = g.n("ShaderNodeNewGeometry").outputs["Normal"]
    dot = g.n("ShaderNodeVectorMath", operation="DOT_PRODUCT")
    g.l(nrm, dot.inputs[0])
    dot.inputs[1].default_value = (-0.5, -0.55, 0.65)
    key = g.remap(dot.outputs["Value"], -0.2, 0.9)
    shade = g.math("ADD", g.math("MULTIPLY", face, 0.35), g.math("MULTIPLY", key, 0.65))
    tint = tuple(p.get("tint", [1.0, 1.0, 1.0]))
    col = g.ramp(shade, [(0.0, tuple(c * 0.45 for c in tint)), (1.0, tint)])
    fade = g.value(1.0)
    g.emit_alpha(col, g.math("MULTIPLY", p.get("strength", 1.2), fade.outputs[0]), 1.0)
    n = int(p.get("blobs", 9))
    rlo, rhi = p.get("radius", [0.12, 0.42])
    spread = p.get("spread", 0.55)
    blobs = []
    for i in range(n):
        bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, segments=24, ring_count=12)
        ob = bpy.context.active_object
        bpy.ops.object.shade_smooth()
        ob.data.materials.append(g.mat)
        a = rng.uniform(0, 6.28)
        d = rng.uniform(0.0, spread) if i > 0 else 0.0
        blobs.append((ob, np.array([math.cos(a) * d, rng.uniform(-0.05, 0.05), math.sin(a) * d]), rng.uniform(rlo, rhi) * (1.3 if i == 0 else 1.0), rng.uniform(0.7, 1.3)))
    rise = p.get("rise", 0.25)

    def update(k):
        fade.outputs[0].default_value = 1.0
        for ob, off, r, speed in blobs:
            swell = 0.5 + 0.5 * ease_out(k * 2.5, 2)
            s = r * swell * max(0.0, 1 - smooth(0.55, 1.0, k * speed)) + 1e-4
            ob.location = tuple(off * (0.6 + 0.6 * ease_out(k, 1.5)) + np.array([0.0, 0.0, rise * k]))
            ob.scale = (s, s, s)

    return update


def _manta_domain(sc, p, rng, fire):
    """a Mantaflow gas domain + an inflow sphere, baked headless (Blender 5.2: bake_all under a temp_override works);
    returns (domain, frames_baked)"""
    frames = int(p.get("bake_frames", 48))
    sc.frame_start, sc.frame_end = 1, frames
    size = p.get("domain", 4.0)
    bpy.ops.mesh.primitive_cube_add(size=size)
    dom = bpy.context.active_object
    dom.name = "Domain"
    mod = dom.modifiers.new("Fluid", "FLUID")
    mod.fluid_type = "DOMAIN"
    d = mod.domain_settings
    d.domain_type = "GAS"
    d.resolution_max = int(p.get("resolution", 64))
    d.use_adaptive_domain = False
    d.use_noise = bool(p.get("noise", False))
    d.alpha = p.get("buoyancy_density", -0.6 if fire else -1.0)  # density buoyancy (negative = rises)
    d.beta = p.get("buoyancy_heat", 2.0)
    d.vorticity = p.get("vorticity", 0.25)
    d.use_dissolve_smoke = True
    d.dissolve_speed = int(p.get("dissolve", 18))
    if fire:
        d.burning_rate = p.get("burning_rate", 0.75)
        d.flame_smoke = p.get("flame_smoke", 1.0)
        d.flame_vorticity = p.get("flame_vorticity", 0.5)
        d.flame_max_temp = p.get("flame_max_temp", 2.0)
    d.cache_type = "ALL"
    cache = os.path.abspath(os.path.join("build", "fxlab", "_cache", f"manta_{int(time.time() * 1000) % 100000}"))
    os.makedirs(cache, exist_ok=True)
    d.cache_directory = cache
    d.cache_frame_start, d.cache_frame_end = 1, frames
    src_r = p.get("emitter", 0.35)
    # emitter_z: where the source sits (fraction of the domain below its centre; 0.42 = on the floor, a rising puff;
    # ~0.1 = mid-air, a ball that blows out in every direction)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=src_r, location=(0, 0, -size * p.get("emitter_z", 0.42)))
    src = bpy.context.active_object
    src.name = "Emitter"
    m2 = src.modifiers.new("Fluid", "FLUID")
    m2.fluid_type = "FLOW"
    f = m2.flow_settings
    f.flow_type = "BOTH" if fire else "SMOKE"
    f.flow_behavior = "INFLOW"
    f.density = p.get("density", 1.0)
    f.temperature = p.get("temperature", 1.2)
    f.fuel_amount = p.get("fuel", 1.0)
    f.use_initial_velocity = True
    f.velocity_normal = p.get("velocity", 1.5)
    f.velocity_random = p.get("velocity_random", 0.6)
    src.hide_render = True
    # a puff: the inflow stops partway so the sheet ends as the smoke thins (one-shot)
    stop = int(frames * p.get("inflow_until", 0.45))
    f.use_inflow = True
    f.keyframe_insert("use_inflow", frame=1)
    f.use_inflow = False
    f.keyframe_insert("use_inflow", frame=max(2, stop))
    f.use_inflow = True
    bpy.context.view_layer.objects.active = dom
    dom.select_set(True)
    with bpy.context.temp_override(object=dom, active_object=dom, selected_objects=[dom]):
        bpy.ops.fluid.bake_all()
    # the volume material: density + (fire) flame -> blackbody, lit by a key sun so the puff has form
    g = Graph("Volume")
    pv = g.n("ShaderNodeVolumePrincipled")
    pv.inputs["Density"].default_value = p.get("render_density", 6.0)
    pv.inputs["Color"].default_value = (*p.get("color", [0.72, 0.72, 0.72]), 1.0)
    pv.inputs["Blackbody Intensity"].default_value = p.get("blackbody", 1.5) if fire else 0.0
    pv.inputs["Temperature"].default_value = p.get("temperature_k", 1500) if fire else 1000  # hotter = whiter flame
    if fire:
        pv.inputs["Blackbody Tint"].default_value = (*p.get("tint", [1.0, 0.55, 0.2]), 1.0)
    g.l(pv.outputs[0], g.out.inputs["Volume"])
    dom.data.materials.append(g.mat)
    # the key light's direction: the default (unchanged), explicit `key_rot` [x, y, z] degrees, or a named `light` - the
    # LIT VARIANTS a game picks from by where its sun is (six-way lighting's Roblox stand-in: bake left / right / top /
    # back / front from ONE spec each, the sprite's `lit` table picks at play time; the camera looks along +Y)
    key_rot = p.get("key_rot") or LIGHTS.get(p.get("light"), (50, 20, -30))
    sun(sc, p.get("key", 3.0), tuple(key_rot), (1.0, 0.95, 0.85)).name = "KeySun"
    sun(sc, p.get("fill", 0.8), (-60, -10, 150), (0.75, 0.8, 1.0))
    return dom, frames


def _volume_update(sc, frames, end=1.0):
    # the first bake frames hold no gas yet (identical empty frames fail the gate): the sheet starts at 8% of the bake;
    # `end` (sheet_end) stops it before the gas thins to nothing (an eroded flipbook ends by its erosion instead)
    first = 1 + int(frames * 0.08)
    last = first + int(round((frames - first) * end))

    def update(k):
        sc.frame_set(first + int(round(k * (last - first))))
    return update


def recipe_smoke_sim(sc, p, rng):
    """OUR OWN smoke: a Mantaflow gas simulation (headless bake, Cycles volume render), lit so the puff has a bright
    side and a shadowed side — a real billowing puff that rises, rolls and thins (one-shot flipbook).
    params: resolution 64, bake_frames 48, domain 4, emitter 0.35, density 1, temperature 1.2, velocity 1.5,
    inflow_until 0.45 (fraction of the bake the inflow runs), dissolve 18, vorticity 0.25, render_density 6,
    color [r,g,b], key 3 (sun), fill 0.8, light left|right|top|back|front (or key_rot [x, y, z]): the key's direction
    for lit variants. Frames are picked evenly across the bake."""
    camera(sc, ortho=p.get("frame", 4.4), loc=(0, -9, 0.35), look=(0, 0, 0.35))  # the domain's lower 40% holds the emitter: the puff rises through the frame
    _, frames = _manta_domain(sc, p, rng, fire=False)
    return _volume_update(sc, frames, p.get("sheet_end", 1.0))


def recipe_fire_sim(sc, p, rng):
    """OUR OWN fire: a Mantaflow fire + smoke simulation (flame -> blackbody emission, smoke above), lit; one-shot
    (the fuel inflow stops at `inflow_until`). params: as smoke_sim + fuel 1, burning_rate 0.75, flame_smoke 1,
    flame_max_temp 2, blackbody 1.5, flame_vorticity 0.5."""
    camera(sc, ortho=p.get("frame", 4.4), loc=(0, -9, 0.35), look=(0, 0, 0.35))
    _, frames = _manta_domain(sc, p, rng, fire=True)
    return _volume_update(sc, frames, p.get("sheet_end", 1.0))


def recipe_shockwave(sc, p, rng):
    """a 3D ground shockwave seen from a low angle: an expanding torus of light with a hot leading edge, rolling
    outward and thinning, plus a flat disc flash under it (an anime impact ring with real perspective — unlike the
    flat `ring` recipe it reads as a 3D wave when placed flat on the ground).
    params: angle 22 (camera elevation, degrees), radius [0.08, 0.95], tube [0.22, 0.06], strength 6,
    color [r,g,b], hot [r,g,b], frame 2.4"""
    ang = math.radians(p.get("angle", 22))
    dist = 7.0
    camera(sc, ortho=p.get("frame", 2.4), loc=(0, -dist * math.cos(ang), dist * math.sin(ang)), look=(0, 0, 0.1))
    bpy.ops.mesh.primitive_torus_add(major_radius=1.0, minor_radius=0.2, major_segments=96, minor_segments=24)
    tor = bpy.context.active_object
    bpy.ops.object.shade_smooth()
    g = Graph("Wave")
    lw = g.n("ShaderNodeLayerWeight", Blend=0.5)
    facing = g.math("SUBTRACT", 1.0, lw.outputs["Facing"], clamp=True)
    k = g.value(1.0)
    strength = g.math("MULTIPLY", g.math("MULTIPLY", g.math("ADD", 0.35, g.math("MULTIPLY", g.math("POWER", facing, 2.0), 1.2)), p.get("strength", 6.0)), k.outputs[0])
    col = g.ramp(facing, [(0.0, tuple(p.get("color", [1.0, 0.6, 0.18]))), (0.6, (1.0, 0.85, 0.5)), (1.0, tuple(p.get("hot", [1.0, 0.98, 0.9])))])
    g.emit_alpha(col, strength, g.math("MULTIPLY", g.remap(facing, 0.0, 0.35, 0.3, 1.0), k.outputs[0]))
    tor.data.materials.append(g.mat)
    bpy.ops.mesh.primitive_circle_add(radius=1.0, vertices=64, fill_type="NGON")
    disc = bpy.context.active_object
    gd = Graph("Flash")
    gen = gd.n("ShaderNodeTexCoord").outputs["Object"]
    ln = gd.n("ShaderNodeVectorMath", operation="LENGTH")
    gd.l(gen, ln.inputs[0])
    kd = gd.value(1.0)
    fall = gd.math("EXPONENT", gd.math("MULTIPLY", gd.math("MULTIPLY", ln.outputs["Value"], ln.outputs["Value"]), -3.0))
    gd.emit_alpha(gd.ramp(fall, [(0.0, tuple(p.get("color", [1.0, 0.6, 0.18]))), (1.0, (1, 1, 1))]), gd.math("MULTIPLY", gd.math("MULTIPLY", fall, 5.0), kd.outputs[0]), gd.math("MULTIPLY", fall, kd.outputs[0]))
    disc.data.materials.append(gd.mat)
    r0, r1 = p.get("radius", [0.08, 0.95])
    t0, t1 = p.get("tube", [0.22, 0.06])

    def update(kk):
        e = ease_out(kk, 2.2)
        R = r0 + (r1 - r0) * e
        T = (t0 + (t1 - t0) * e) * (1 + 0.6 * (1 - kk))
        tor.scale = (R, R, T / 0.2)  # ring radius R, tube height T (the unit torus tube is 0.2)
        k.outputs[0].default_value = max(0.0, 1 - kk) ** 1.2
        kd.outputs[0].default_value = max(0.0, 1 - kk / 0.35) ** 2
        disc.scale = (0.25 + 0.75 * e, 0.25 + 0.75 * e, 1)

    return update


def recipe_glyph(sc, p, rng):
    """a magic circle decal from above: concentric rings, tick marks, a polygon star, and runes (glowing text in the
    outer band) — one still (frames 1) or a slow rotation across the sheet (frames 8 + `spin`). params: rings 3,
    ticks 24, star 6 (0 = none), runes "ᚠᚢᚦᚨᚱᚲ..." (any text; `font` = a .ttf path, default Segoe UI Historic on Windows), color [r,g,b], strength 4, spin 15 (deg)"""
    camera(sc, ortho=2.2, loc=(0, 0, 6), look=(0, 0, 0))
    root = bpy.data.objects.new("Glyph", None)
    sc.collection.objects.link(root)
    g = Graph("Glyph")
    kg = g.value(1.0)
    col_rgb = tuple(p.get("color", [1.0, 0.8, 0.35]))
    g.emit_alpha(g.ramp(kg.outputs[0], [(0.0, col_rgb), (1.0, col_rgb)]), g.math("MULTIPLY", p.get("strength", 4.0), kg.outputs[0]), 1.0)
    mat = g.mat

    def ring(r, w):
        bpy.ops.mesh.primitive_torus_add(major_radius=r, minor_radius=w, major_segments=128, minor_segments=8)
        ob = bpy.context.active_object
        ob.data.materials.append(mat)
        ob.parent = root
        return ob

    n_rings = int(p.get("rings", 3))
    for i in range(n_rings):
        ring(0.95 - i * 0.22, 0.012 if i else 0.02)
    ticks = int(p.get("ticks", 24))
    for i in range(ticks):
        a = i / ticks * math.tau
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(math.cos(a) * 0.84, math.sin(a) * 0.84, 0))
        ob = bpy.context.active_object
        ob.scale = (0.06 if i % 4 == 0 else 0.03, 0.012, 0.01)
        ob.rotation_euler = (0, 0, a)
        ob.data.materials.append(mat)
        ob.parent = root
    star = int(p.get("star", 6))
    if star > 1:
        pts = [(math.cos(i / star * math.tau + math.pi / 2) * 0.5, math.sin(i / star * math.tau + math.pi / 2) * 0.5, 0) for i in range(star)]
        step = 2 if star >= 5 else 1
        for i in range(star):
            a_, b_ = pts[i], pts[(i + step) % star]
            mid = ((a_[0] + b_[0]) / 2, (a_[1] + b_[1]) / 2, 0)
            L = math.dist(a_, b_)
            bpy.ops.mesh.primitive_cube_add(size=1.0, location=mid)
            ob = bpy.context.active_object
            ob.scale = (L, 0.012, 0.01)
            ob.rotation_euler = (0, 0, math.atan2(b_[1] - a_[1], b_[0] - a_[0]))
            ob.data.materials.append(mat)
            ob.parent = root
    runes = p.get("runes", "ᚠᚢᚦᚨᚱᚲᚷᚹᚺᚾᛁᛃᛇᛈᛉᛊᛏᛒᛖᛗᛚᛜᛞᛟ")
    # Blender's built-in font has no runic range (it renders boxes): use a font that does when one is installed
    font = None
    for cand in [p.get("font")] + ["C:/Windows/Fonts/seguihis.ttf", "/usr/share/fonts/truetype/noto/NotoSansRunic-Regular.ttf"]:
        if cand and os.path.isfile(cand):
            font = bpy.data.fonts.load(cand)
            break
    n = len(runes)
    for i, ch in enumerate(runes):
        a = i / n * math.tau
        cu = bpy.data.curves.new("Rune", "FONT")
        cu.body = ch
        cu.size = 0.09
        cu.align_x = "CENTER"
        cu.align_y = "CENTER"
        cu.extrude = 0.004
        if font:
            cu.font = font
        ob = bpy.data.objects.new("Rune", cu)
        sc.collection.objects.link(ob)
        ob.location = (math.cos(a) * 0.62, math.sin(a) * 0.62, 0)
        ob.rotation_euler = (0, 0, a - math.pi / 2)
        ob.data.materials.append(mat)
        ob.parent = root
    spin = math.radians(p.get("spin", 15))

    def update(k):
        root.rotation_euler = (0, 0, spin * k)
        kg.outputs[0].default_value = 1.0

    return update


def recipe_circle(sc, p, rng):
    """a Fate-style magic circle from above, drawn from a layout (radius 1 = the circle's edge):
    rings [[r, w], ...]; polys [[n, r, step, w, rot_deg], ...] (n points joined every `step`: [6, r, 2] a hexagram,
    [5, r, 2] a pentagram, [4, r, 1] a square); bands [[r, size, "text", "font path"?], ...] (runes / letters set
    around a circle, upright to it); ticks [[count, r, long, short], ...]; sats [[count, r, size, star_n], ...] (small
    circles on a ring, each with its own star); dots [[count, r, size], ...]; color [r, g, b], strength 4, spin 0 (deg
    across the sheet). One still by default; tint it per layer."""
    camera(sc, ortho=2.2, loc=(0, 0, 6), look=(0, 0, 0))
    root = bpy.data.objects.new("Circle", None)
    sc.collection.objects.link(root)
    g = Graph("Circle")
    kg = g.value(1.0)
    col_rgb = tuple(p.get("color", [1.0, 0.92, 0.7]))
    g.emit_alpha(g.ramp(kg.outputs[0], [(0.0, col_rgb), (1.0, col_rgb)]), g.math("MULTIPLY", p.get("strength", 4.0), kg.outputs[0]), 1.0)
    mat = g.mat

    def own(ob):
        ob.data.materials.append(mat)
        ob.parent = root
        return ob

    def ring(r, w):
        bpy.ops.mesh.primitive_torus_add(major_radius=r, minor_radius=w, major_segments=192, minor_segments=6)
        return own(bpy.context.active_object)

    def seg(a, b, w):
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, 0)
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=mid)
        ob = bpy.context.active_object
        ob.scale = (math.dist(a, b) + w, w, 0.01)
        ob.rotation_euler = (0, 0, math.atan2(b[1] - a[1], b[0] - a[0]))
        return own(ob)

    def poly(n, r, step, w, rot=0.0, cx=0.0, cy=0.0):
        r0 = math.radians(rot) + math.pi / 2
        pts = [(cx + math.cos(r0 + i / n * math.tau) * r, cy + math.sin(r0 + i / n * math.tau) * r) for i in range(n)]
        for i in range(n):
            seg(pts[i], pts[(i + step) % n], w)

    fonts = {}

    def font_for(path):
        for cand in [path, "C:/Windows/Fonts/seguihis.ttf", "/usr/share/fonts/truetype/noto/NotoSansRunic-Regular.ttf"]:
            if cand and os.path.isfile(cand):
                if cand not in fonts:
                    fonts[cand] = bpy.data.fonts.load(cand)
                return fonts[cand]
        return None

    for r, w in p.get("rings", [[0.97, 0.012], [0.93, 0.005], [0.72, 0.008]]):
        ring(r, w)
    for pl in p.get("polys", [[6, 0.72, 2, 0.008, 0]]):
        n, r, step = int(pl[0]), pl[1], int(pl[2])
        poly(n, r, step, pl[3] if len(pl) > 3 else 0.008, pl[4] if len(pl) > 4 else 0)
    for b in p.get("bands", [[0.83, 0.075, "ᚠᚢᚦᚨᚱᚲᚷᚹᚺᚾᛁᛃᛇᛈᛉᛊᛏᛒᛖᛗᛚᛜᛞᛟ"]]):
        r, size, text = b[0], b[1], b[2]
        fnt = font_for(b[3] if len(b) > 3 else None)
        n = len(text)
        for i, ch in enumerate(text):
            if ch == " ":
                continue
            a = math.pi / 2 - i / n * math.tau  # clockwise from the top: the text reads left to right along the rim
            cu = bpy.data.curves.new("Rune", "FONT")
            cu.body = ch
            cu.size = size
            cu.align_x = "CENTER"
            cu.align_y = "CENTER"
            cu.extrude = 0.003
            if fnt:
                cu.font = fnt
            ob = bpy.data.objects.new("Rune", cu)
            sc.collection.objects.link(ob)
            ob.location = (math.cos(a) * r, math.sin(a) * r, 0)
            ob.rotation_euler = (0, 0, a - math.pi / 2)
            own(ob)
    for t in p.get("ticks", []):
        count, r, lng, sht = int(t[0]), t[1], t[2], t[3]
        for i in range(count):
            a = i / count * math.tau
            L = lng if i % 4 == 0 else sht
            seg((math.cos(a) * r, math.sin(a) * r), (math.cos(a) * (r - L), math.sin(a) * (r - L)), 0.006)
    for s in p.get("sats", []):
        count, r, size = int(s[0]), s[1], s[2]
        star = int(s[3]) if len(s) > 3 else 0
        for i in range(count):
            a = i / count * math.tau + math.pi / 2
            cx, cy = math.cos(a) * r, math.sin(a) * r
            bpy.ops.mesh.primitive_torus_add(major_radius=size, minor_radius=0.006, major_segments=96, minor_segments=6, location=(cx, cy, 0))
            own(bpy.context.active_object)
            bpy.ops.mesh.primitive_torus_add(major_radius=size * 0.78, minor_radius=0.003, major_segments=96, minor_segments=6, location=(cx, cy, 0))
            own(bpy.context.active_object)
            if star > 2:
                poly(star, size * 0.78, 2 if star >= 5 else 1, 0.004, math.degrees(a), cx, cy)
    for d in p.get("dots", []):
        count, r, size = int(d[0]), d[1], d[2]
        for i in range(count):
            a = (i + 0.5) / count * math.tau
            bpy.ops.mesh.primitive_uv_sphere_add(radius=size, segments=16, ring_count=8, location=(math.cos(a) * r, math.sin(a) * r, 0))
            own(bpy.context.active_object)
    spin = math.radians(p.get("spin", 0))

    def update(k):
        root.rotation_euler = (0, 0, spin * k)

    return update


def recipe_blackhole(sc, p, rng):
    """a black hole (Gargantua): a black core, a tilted accretion disc of swirling filaments (white-hot inner edge,
    gold, orange, deep red outside), brighter on the side turning toward the camera (doppler), the far side of the
    disc lensed into an arc over and under the core, and a thin photon ring. params: tilt 8 (camera elevation above
    the disc, deg), core 0.34, inner 0.44, outer 1.3, lens 0.8 (the lensed arc's outer radius), arms 3, twist 2.4,
    strength 9; the swirl turns 1/arms of a revolution across the sheet, so a Loop flipbook never jumps."""
    tilt = math.radians(p.get("tilt", 8))
    dist = 6.0
    camera(sc, loc=(0, -dist * math.cos(tilt), dist * math.sin(tilt)), look=(0, 0, 0), lens=p.get("camera_lens", 55))
    core, rin, rout, rlens = p.get("core", 0.34), p.get("inner", 0.44), p.get("outer", 1.3), p.get("lens", 0.8)
    arms, twist, strength = int(p.get("arms", 3)), p.get("twist", 2.4), p.get("strength", 9.0)
    frames = max(1, int(p.get("_frames", 16)))

    # the core: pure black, opaque (coverage 1, no light) -> the finish keeps it black and solid
    bpy.ops.mesh.primitive_uv_sphere_add(radius=core, segments=64, ring_count=32)
    ball = bpy.context.active_object
    bm = bpy.data.materials.new("Core")
    bm.use_nodes = True
    nt = bm.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (0, 0, 0, 1)
    em.inputs["Strength"].default_value = 0.0
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    ball.data.materials.append(bm)

    def annulus(name, r0, r1, seg=256, rings=32):
        verts, faces = [], []
        for j in range(rings + 1):
            r = r0 + (r1 - r0) * j / rings
            for i in range(seg):
                a = i / seg * math.tau
                verts.append((math.cos(a) * r, math.sin(a) * r, 0))
        for j in range(rings):
            for i in range(seg):
                a, b = j * seg + i, j * seg + (i + 1) % seg
                faces.append((a, b, b + seg, a + seg))
        return mesh_object(sc, name, verts, faces)

    def swirl_mat(name, r0, r1, power, gain, doppler):
        g = Graph(name)
        tc = g.n("ShaderNodeTexCoord")
        sep = g.n("ShaderNodeSeparateXYZ")
        g.l(tc.outputs["Object"], sep.inputs[0])
        x, y = sep.outputs["X"], sep.outputs["Y"]
        r = g.math("SQRT", g.math("ADD", g.math("MULTIPLY", x, x), g.math("MULTIPLY", y, y)))
        th = g.math("ARCTAN2", y, x)
        a = g.math("MULTIPLY", g.math("ADD", th, g.math("MULTIPLY", r, twist)), float(arms))
        cmb = g.n("ShaderNodeCombineXYZ")
        g.l(g.math("MULTIPLY", g.math("COSINE", a), 1.4), cmb.inputs["X"])
        g.l(g.math("MULTIPLY", g.math("SINE", a), 1.4), cmb.inputs["Y"])
        g.l(g.math("MULTIPLY", r, 11.0), cmb.inputs["Z"])
        nz = g.n("ShaderNodeTexNoise", Scale=1.7, Detail=10.0, Roughness=0.62)
        g.l(cmb.outputs[0], nz.inputs["Vector"])
        fil = g.remap(nz.outputs["Fac"], 0.32, 0.78)  # the filaments
        rr = g.remap(r, r0, r1)  # 0 at the inner edge -> 1 outside
        fall = g.math("POWER", g.math("SUBTRACT", 1.0, rr), power)
        edge = g.remap(r, r0, r0 + 0.035)  # a crisp inner edge
        inten = g.math("MULTIPLY", g.math("MULTIPLY", fall, edge), g.math("ADD", 0.28, g.math("MULTIPLY", fil, 0.72)))
        if doppler:
            geo = g.n("ShaderNodeNewGeometry")
            sp = g.n("ShaderNodeSeparateXYZ")
            g.l(geo.outputs["Position"], sp.inputs[0])
            inten = g.math("MULTIPLY", inten, g.remap(sp.outputs["X"], -r1, r1, 1.75, 0.45))
        inten = g.math("MULTIPLY", inten, gain)
        col = g.ramp(rr, [(0.0, (1.0, 0.98, 0.92)), (0.12, (1.0, 0.82, 0.42)), (0.42, (1.0, 0.5, 0.12)), (1.0, (0.55, 0.08, 0.02))])
        g.emit_alpha(col, g.math("MULTIPLY", inten, strength), g.math("MINIMUM", g.math("MULTIPLY", inten, 1.8), 1.0))
        return g.mat

    disc = annulus("Disc", rin, rout)
    disc.data.materials.append(swirl_mat("DiscM", rin, rout, 1.5, 1.0, True))
    # the lensed far side: the same disc bent around the core, seen as a ring facing the camera
    halo = annulus("Lens", core * 1.04, rlens, rings=20)
    halo.data.materials.append(swirl_mat("LensM", core * 1.04, rlens, 3.2, 1.1, True))  # a thin bright arc, no grey haze
    halo.rotation_euler = (math.pi / 2 - tilt, 0, 0)
    # the photon ring: a thin white line hugging the core
    bpy.ops.mesh.primitive_torus_add(major_radius=core * 1.02, minor_radius=0.006, major_segments=256, minor_segments=8)
    ring = bpy.context.active_object
    ring.rotation_euler = (math.pi / 2 - tilt, 0, 0)
    gr = Graph("Photon")
    kv = gr.value(1.0)
    gr.emit_alpha(gr.ramp(kv.outputs[0], [(0.0, (1, 0.97, 0.9)), (1.0, (1, 0.97, 0.9))]), strength * 1.6, 1.0)
    ring.data.materials.append(gr.mat)
    period = math.tau / arms

    def update(k):
        ang = period * k * (frames - 1) / frames  # the last frame stops one step short of the first: a seamless loop
        disc.rotation_euler = (0, 0, ang)
        halo.rotation_euler = (math.pi / 2 - tilt, ang, 0)

    return update


def recipe_streak(sc, p, rng):
    """ONE clean straight streak, upright in a square cell, for VelocityParallel particles (the image's up runs along
    the flight): a thin gaussian line, its HEAD hot at the top, its tail fading to nothing toward the bottom - a spark
    line, a ricochet, a flung drop's motion blur. (The Kenney sparks are zigzags and the `rays` recipe draws a glowing
    source at its foot: both read as blobs in flight - Sample Game 2026-10-29.)
    params: width 0.035 (the gaussian half-width, cell units), head 0.85 (where the head sits, 0 bottom .. 1 top),
    tail 0.7 (how far down the tail reaches from the head), core 0.4 (a hotter thin core, 0 = none), strength 4,
    color [r,g,b] (the line), hot [r,g,b] (the core)"""
    camera(sc, ortho=2.0, loc=(0, -5, 0))
    ob = mesh_object(sc, "Plate", [(-1, 0, -1), (1, 0, -1), (1, 0, 1), (-1, 0, 1)], [(0, 1, 2, 3)], [(0, 0), (1, 0), (1, 1), (0, 1)])
    g = Graph("Streak")
    obj = g.n("ShaderNodeTexCoord").outputs["Object"]
    sep = g.n("ShaderNodeSeparateXYZ")
    g.l(obj, sep.inputs[0])
    x = sep.outputs["X"]
    v = g.remap(sep.outputs["Z"], -1.0, 1.0)  # 0 bottom .. 1 top
    w = p.get("width", 0.035) * 2.0  # cell units -> plate units (the plate spans -1..1)
    across = g.math("EXPONENT", g.math("MULTIPLY", g.math("MULTIPLY", x, x), -1.0 / (w * w)))
    head, tail = p.get("head", 0.85), p.get("tail", 0.7)
    # along: 0 below the tail's end, rising to 1 at the head, a quick soft cap just past it
    along = g.math("MULTIPLY", g.math("POWER", g.remap(v, head - tail, head), 1.6), g.remap(v, head + 0.08, head, 0.0, 1.0))
    inten = g.math("MULTIPLY", across, along)
    core_w = w * p.get("core", 0.4)
    if core_w > 0:
        core = g.math("EXPONENT", g.math("MULTIPLY", g.math("MULTIPLY", x, x), -1.0 / (core_w * core_w)))
        inten = g.math("ADD", inten, g.math("MULTIPLY", g.math("MULTIPLY", core, along), 0.8))
    col = g.ramp(g.math("MULTIPLY", inten, 0.6), [(0.0, tuple(p.get("color", [1.0, 0.9, 0.75]))), (1.0, tuple(p.get("hot", [1.0, 1.0, 1.0])))])
    g.emit_alpha(col, g.math("MULTIPLY", inten, p.get("strength", 4.0)), 1.0)
    ob.data.materials.append(g.mat)
    return lambda k: None


def recipe_gradient(sc, p, rng):
    """a pure glow strip for Beams / tubes: a gaussian across the width (nothing else — no noise body that adds up
    to a brown slab on a double-sided tube), optional soft hot core, fades to NOTHING at the edges.
    params: aspect 4, band 0.16 (gaussian width in strip units; the half-height is 1/aspect), core 0.03 (0 = none),
    strength 3, gold [r,g,b] (the band), hot [r,g,b] (the core), along 0 (0..1: a soft fade of the strip's ends)"""
    aspect = p.get("aspect", 4)
    sc.render.resolution_y = int(sc.render.resolution_x / aspect)
    camera(sc, ortho=2.0, loc=(0, -5, 0))
    ob = mesh_object(sc, "Plate", [(-1, 0, -1 / aspect), (1, 0, -1 / aspect), (1, 0, 1 / aspect), (-1, 0, 1 / aspect)], [(0, 1, 2, 3)], [(0, 0), (1, 0), (1, 1), (0, 1)])
    g = Graph("Gradient")
    obj = g.n("ShaderNodeTexCoord").outputs["Object"]
    sep = g.n("ShaderNodeSeparateXYZ")
    g.l(obj, sep.inputs[0])
    y = sep.outputs["Z"]
    sq = g.math("MULTIPLY", y, y)
    bw, cw = p.get("band", 0.16), p.get("core", 0.03)
    band = g.math("EXPONENT", g.math("MULTIPLY", sq, -1.0 / (bw * bw)))
    inten = band
    if cw > 0:
        core = g.math("EXPONENT", g.math("MULTIPLY", sq, -1.0 / (cw * cw)))
        inten = g.math("ADD", band, g.math("MULTIPLY", core, 1.5))
    along = p.get("along", 0.0)
    if along > 0:
        x = sep.outputs["X"]
        ends = g.math("MULTIPLY", g.remap(x, -1.0, -1.0 + along), g.remap(x, 1.0, 1.0 - along))
        inten = g.math("MULTIPLY", inten, ends)
    col = g.ramp(g.math("MULTIPLY", inten, 0.6), [(0.0, tuple(p.get("gold", [1.0, 0.8, 0.4]))), (1.0, tuple(p.get("hot", [1.0, 0.97, 0.88])))])
    g.emit_alpha(col, g.math("MULTIPLY", inten, p.get("strength", 3.0)), 1.0)
    ob.data.materials.append(g.mat)
    return lambda k: None


def recipe_smear(sc, p, rng):
    """a blade's MOTION SMEAR as a trail strip (character-action 5's Greatsword cuts, refs_measured/greatsword_slash.beats.md
    beat 0): u runs along the trail (u = 1 the newest edge at the blade, u = 0 the oldest), v across it (v = 0 the hilt,
    v = 1 the tip) - the kit's trail UVs (player TrailLayer, VfxStage trail). Two layers of one smear:
    layer "ink": the smear's BODY - a plum-black, semi-opaque sweep, thicker toward the tip (the tip moves fastest),
    streaked along the swing and tearing into smoke wisps toward the old end (use with alpha "coverage", non-additive);
    layer "edge": the HOT LEADING LINE near the tip with a chromatic (rainbow) fringe - red, a cool line inside, a warm
    one outside - bright at the new end, dying toward the old (use with alpha "glow", additive).
    params: layer "ink", aspect 4, ink [r,g,b], smoke [r,g,b] (the blurred steel between the ink streaks), tint [r,g,b] (the dark red the ink turns toward the edge),
    edge [r,g,b], hot [r,g,b], cool [r,g,b], warm [r,g,b], line 0.93 (v of the hot line), tear 0.65 (how much of the
    old end frays away), streak 18 (streaks across the width), fill 0.3 (lower = a fuller body), floor 0.55 (the\n    thinnest a streak gets), strength 3, wall false (a crown / tube WALL band instead: the torn old end at the TOP of the
    image, the crisp front at the bottom, streaks running UP, whole all the way across - a blast's smoke wall, ink only)"""
    aspect = p.get("aspect", 4)
    sc.render.resolution_y = int(sc.render.resolution_x / aspect)
    camera(sc, ortho=2.0, loc=(0, -5, 0))
    ob = mesh_object(sc, "Plate", [(-1, 0, -1 / aspect), (1, 0, -1 / aspect), (1, 0, 1 / aspect), (-1, 0, 1 / aspect)], [(0, 1, 2, 3)], [(0, 0), (1, 0), (1, 1), (0, 1)])
    g = Graph("Smear")
    obj = g.n("ShaderNodeTexCoord").outputs["Object"]
    sep = g.n("ShaderNodeSeparateXYZ")
    g.l(obj, sep.inputs[0])
    wall = bool(p.get("wall", False))
    if wall:  # u runs DOWN the image (0 = the torn top .. 1 = the crisp foot), v across it
        u = g.remap(sep.outputs["Z"], 1.0 / aspect, -1.0 / aspect)
        v = g.remap(sep.outputs["X"], -1.0, 1.0)
    else:
        u = g.remap(sep.outputs["X"], -1.0, 1.0)  # 0 old end .. 1 the blade
        v = g.remap(sep.outputs["Z"], -1.0 / aspect, 1.0 / aspect)  # 0 hilt .. 1 tip
    # streaks ALONG the swing: noise stretched along u (few cells along, many across)
    c = g.n("ShaderNodeCombineXYZ")
    g.l(g.math("MULTIPLY", u, 2.2), c.inputs["X"])
    g.l(g.math("MULTIPLY", v, float(p.get("streak", 18))), c.inputs["Y"])
    nz = g.n("ShaderNodeTexNoise", Scale=1.0, Detail=6.0, Roughness=0.62, noise_dimensions="4D")
    g.l(c.outputs[0], nz.inputs["Vector"])
    nz.inputs["W"].default_value = rng.uniform(0, 40)
    streak = nz.outputs["Factor"]
    # a slower billow for the smoke the old end tears into
    c2 = g.n("ShaderNodeCombineXYZ")
    g.l(g.math("MULTIPLY", u, 5.0), c2.inputs["X"])
    g.l(g.math("MULTIPLY", v, 4.0), c2.inputs["Y"])
    nz2 = g.n("ShaderNodeTexNoise", Scale=1.0, Detail=4.0, Roughness=0.55, noise_dimensions="4D")
    g.l(c2.outputs[0], nz2.inputs["Vector"])
    nz2.inputs["W"].default_value = rng.uniform(0, 40)
    billow = nz2.outputs["Factor"]
    line = p.get("line", 0.93)
    if p.get("layer", "ink") == "ink":
        # across: faint at the hilt, full toward the tip, a clean cut just past the hot line
        across = g.math("MULTIPLY", g.remap(v, 0.04, 0.55), g.remap(v, line + 0.035, line + 0.055, 1.0, 0.0))
        # along: whole at the blade, the old end frays - the keep threshold rises toward u = 0
        old = g.math("POWER", g.math("SUBTRACT", 1.0, u), 1.4)
        thr = g.math("ADD", p.get("fill", 0.30), g.math("MULTIPLY", old, p.get("tear", 0.65)))
        mixn = g.math("ADD", g.math("MULTIPLY", streak, 0.55), g.math("MULTIPLY", billow, 0.45))
        keep = g.remap(g.math("SUBTRACT", mixn, thr), -0.08, 0.06)
        head = g.remap(u, 0.985, 1.0, 1.0, 0.0)  # a crisp front
        alpha = g.math("MULTIPLY", keep, head) if wall else g.math("MULTIPLY", g.math("MULTIPLY", across, keep), head)
        alpha = g.math("MULTIPLY", alpha, g.remap(streak, 0.25, 0.6, p.get("floor", 0.55), 1.0))  # density varies along the streaks
        # colour: the blurred steel reads as a smoky grey (character-action 3.51 s: a pale translucent sweep), cut by plum ink
        # streaks (8.70 s); it turns dark red toward the hot line - two tones so it reads on a dark arena AND a pale one
        body = g.ramp(g.remap(streak, 0.3, 0.7), [(0.0, tuple(p.get("ink", [0.078, 0.047, 0.067]))), (0.45, tuple(p.get("ink", [0.078, 0.047, 0.067]))),
                                                  (1.0, tuple(p.get("smoke", [0.078, 0.047, 0.067])))])
        toward = g.remap(v, line - 0.2, line)
        mix = g.n("ShaderNodeMix", data_type="RGBA", blend_type="MIX")
        g.l(g.math("POWER", toward, 2.0), mix.inputs["Factor"])
        g.l(body, mix.inputs[6])
        mix.inputs[7].default_value = tuple(p.get("tint", [0.28, 0.07, 0.1])) + (1,)
        g.emit_alpha(mix.outputs[2], 1.0, alpha)
    else:
        def band(at, width):
            d = g.math("SUBTRACT", v, at)
            return g.math("EXPONENT", g.math("MULTIPLY", g.math("MULTIPLY", d, d), -1.0 / (width * width)))
        hot = band(line, p.get("width", 0.024))
        cool = g.math("MULTIPLY", band(line - 0.045, 0.012), 0.55)
        warm = g.math("MULTIPLY", band(line + 0.032, 0.010), 0.6)
        along = g.math("POWER", u, p.get("falloff", 1.6))  # bright at the blade, dying toward the old end
        broken = g.remap(streak, 0.28, 0.62, 0.25, 1.0)
        fade = g.math("MULTIPLY", along, broken)
        def tint(intensity, rgb):
            m = g.n("ShaderNodeMix", data_type="RGBA", blend_type="MULTIPLY")
            m.inputs["Factor"].default_value = 1.0
            g.l(intensity, m.inputs[6])
            m.inputs[7].default_value = (rgb[0], rgb[1], rgb[2], 1)
            return m.outputs[2]
        heat = g.math("MULTIPLY", hot, g.remap(u, 0.6, 1.0))  # the core whitens only near the blade
        core = g.ramp(heat, [(0.0, tuple(p.get("edge", [0.79, 0.3, 0.37]))), (1.0, tuple(p.get("hot", [0.92, 0.59, 0.71])))])
        hot_col = g.n("ShaderNodeMix", data_type="RGBA", blend_type="MULTIPLY")
        hot_col.inputs["Factor"].default_value = 1.0
        g.l(core, hot_col.inputs[6])
        g.l(hot, hot_col.inputs[7])
        add1 = g.n("ShaderNodeMix", data_type="RGBA", blend_type="ADD")
        add1.inputs["Factor"].default_value = 1.0
        g.l(hot_col.outputs[2], add1.inputs[6])
        g.l(tint(cool, p.get("cool", [0.25, 0.45, 1.0])), add1.inputs[7])
        add2 = g.n("ShaderNodeMix", data_type="RGBA", blend_type="ADD")
        add2.inputs["Factor"].default_value = 1.0
        g.l(add1.outputs[2], add2.inputs[6])
        g.l(tint(warm, p.get("warm", [1.0, 0.75, 0.3])), add2.inputs[7])
        inten = g.math("MULTIPLY", g.math("ADD", g.math("ADD", hot, cool), warm), fade)
        g.emit_alpha(add2.outputs[2], g.math("MULTIPLY", fade, p.get("strength", 3.0)), g.math("MINIMUM", inten, 1.0))
    ob.data.materials.append(g.mat)
    return lambda k: None


RECIPES = {
    "smear": recipe_smear,
    "streak": recipe_streak,
    "gradient": recipe_gradient,
    "circle": recipe_circle,
    "blackhole": recipe_blackhole,
    "smoke_sim": recipe_smoke_sim,
    "fire_sim": recipe_fire_sim,
    "shockwave": recipe_shockwave,
    "glyph": recipe_glyph,
    "lightning": recipe_lightning,
    "slash": recipe_slash,
    "shards": recipe_shards,
    "cel": recipe_cel,
    "wave": recipe_wave,
    "rays": recipe_rays,
    "ring": recipe_ring,
    "burst": recipe_burst,
    "wind": recipe_wind,
    "dust": recipe_dust,
    "flow": recipe_flow,
    "crack": recipe_crack,
    "blast": recipe_blast,
}


# ---------------------------------------------------------------- import (frames from a vetted pack)

IMPORT_EXT = (".exr", ".png", ".tga", ".jpg", ".jpeg", ".tif", ".tiff", ".hdr")


def import_frames(name, spec, out_dir):
    """recipe "import": the frames of a downloaded, VETLOG-recorded pack become this texture's frames.
    spec: "source": a directory (every image in it, sorted) or one image file; "select": {"start": 1, "step": 4,
    "count": 16} picks frames (1-based start, every `step`-th, `count` of them; default: `frames` spread evenly);
    "cell": 256 resizes every frame to cell x cell (sheet = cell x grid, <= 1024); "crop": [x0, y0, x1, y1] as fractions of the image; "premultiply": true when the file is straight alpha over
    black (PNG sprites). Loaded through Blender (EXR stays linear HDR; PNG/TGA go through the colour manager to
    scene linear) and written as the same npy frames a render produces."""
    src = spec.get("source")
    if not src:
        raise ValueError('recipe "import" needs "source": a directory of frames or one image (see VETLOG.md)')
    src = os.path.abspath(src)
    if os.path.isdir(src):
        files = sorted(os.path.join(src, f) for f in os.listdir(src) if f.lower().endswith(IMPORT_EXT))
    elif os.path.isfile(src):
        files = [src]
    else:
        raise ValueError(f"source {src} does not exist")
    if not files:
        raise ValueError(f"no image frames in {src}")
    sel = spec.get("select") or {}
    want = int(spec.get("frames", 1))
    if sel:
        start, step, count = int(sel.get("start", 1)) - 1, int(sel.get("step", 1)), int(sel.get("count", want))
        files = files[start::step][:count]
    elif len(files) > want:
        files = [files[int(i * (len(files) - 1) / max(1, want - 1))] for i in range(want)] if want > 1 else [files[len(files) // 2]]
    crop = spec.get("crop")
    fdir = os.path.join(out_dir, name)
    os.makedirs(fdir, exist_ok=True)
    for f in os.listdir(fdir):
        if f.endswith(".npy"):
            os.remove(os.path.join(fdir, f))
    cell = int(spec.get("cell", 0))
    grid = int(spec.get("grid", 1))
    if len(files) == 1 and want > 1 and grid > 1:
        # ONE image with frames > 1 is a finished SHEET (grid x grid cells, row by row from the top left): slice it into
        # its frames (2026-10-24: it was taken as one frame and shrunk into cell 0 - bloom_grow, frost_grow, kanada_flare
        # and the flowbake sheets played their whole sheet tiny for one frame, then nothing)
        img = bpy.data.images.load(files[0])
        w, h = img.size
        px = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
        bpy.data.images.remove(img)
        arr = px.reshape(h, w, 4)[::-1]
        cw, ch = w // grid, h // grid
        side = cell or cw
        for i in range(min(want, grid * grid)):
            r, c = divmod(i, grid)
            fr = arr[r * ch:(r + 1) * ch, c * cw:(c + 1) * cw]
            if (ch, cw) != (side, side):
                if ch % side == 0 and cw % side == 0:  # block-average down
                    fr = fr.reshape(side, ch // side, side, cw // side, 4).mean(axis=(1, 3))
                else:  # nearest
                    fr = fr[(np.arange(side) * ch // side)][:, (np.arange(side) * cw // side)]
            if spec.get("premultiply"):
                fr = fr.copy()
                fr[..., :3] *= fr[..., 3:4]
            np.save(os.path.join(fdir, f"{i:03d}.npy"), fr.astype(np.float16))
        n = min(want, grid * grid)
        with open(os.path.join(fdir, "frames.json"), "w", encoding="utf-8") as fh:
            json.dump({"frames": n, "spec_mtime": os.path.getmtime(spec["_path"]), "source": src, "files": [os.path.basename(files[0])], "sheet": grid}, fh)
        return n
    for i, path in enumerate(files):
        img = bpy.data.images.load(path)
        if cell and tuple(img.size) != (cell, cell):  # the sheet must be cell x grid <= 1024 (Roblox downscales above)
            img.scale(cell, cell)
        w, h = img.size
        px = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
        bpy.data.images.remove(img)
        arr = px.reshape(h, w, 4)[::-1]
        if crop:
            x0, y0, x1, y1 = [max(0.0, min(1.0, float(c))) for c in crop]
            arr = arr[int(y0 * h) : max(int(y0 * h) + 1, int(y1 * h)), int(x0 * w) : max(int(x0 * w) + 1, int(x1 * w))]
        if spec.get("premultiply"):
            arr = arr.copy()
            arr[..., :3] *= arr[..., 3:4]
        np.save(os.path.join(fdir, f"{i:03d}.npy"), arr.astype(np.float16))
    with open(os.path.join(fdir, "frames.json"), "w", encoding="utf-8") as fh:
        json.dump({"frames": len(files), "spec_mtime": os.path.getmtime(spec["_path"]), "source": src, "files": [os.path.basename(f) for f in files]}, fh)
    return len(files)


# ---------------------------------------------------------------- render


def aura_frames(name, spec, out_dir):
    """recipe "aura": ki auras and their elements from primitives (kit/vfx/aura.py, numpy only) — no Blender render"""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import aura  # noqa: E402

    fdir = os.path.join(out_dir, name)
    os.makedirs(fdir, exist_ok=True)
    for f in os.listdir(fdir):
        if f.endswith(".npy"):
            os.remove(os.path.join(fdir, f))
    frames = aura.frames(spec)
    for i, f in enumerate(frames):
        np.save(os.path.join(fdir, f"{i:03d}.npy"), f.astype(np.float16))
    with open(os.path.join(fdir, "frames.json"), "w", encoding="utf-8") as fh:
        json.dump({"frames": len(frames), "spec_mtime": os.path.getmtime(spec["_path"]), "gen_mtime": os.path.getmtime(aura.__file__)}, fh)
    return len(frames)


LIT_DONE = set()  # lit variants written by their sim's render this run


def render(name, spec, out_dir):
    recipe = spec.get("recipe")
    if recipe == "import":
        return import_frames(name, spec, out_dir)
    if recipe == "aura":
        return aura_frames(name, spec, out_dir)
    if recipe not in RECIPES:
        raise ValueError(f"recipe must be one of import, {', '.join(RECIPES)}")
    p = spec.get("params", {})
    cell = int(spec.get("cell", 256))
    frames = int(spec.get("frames", 1))
    sc = new_scene(cell, cell, int(spec.get("samples", 32)), volume=recipe in ("dust", "smoke_sim", "fire_sim"))
    p = dict(p, _frames=frames)  # a recipe that loops needs the frame count
    update = RECIPES[recipe](sc, p, random.Random(int(spec.get("seed", 1))))
    fdir = os.path.join(out_dir, name)
    os.makedirs(fdir, exist_ok=True)
    for f in os.listdir(fdir):
        if f.endswith(".npy"):
            os.remove(os.path.join(fdir, f))
    tmp = os.path.join(fdir, "_frame.exr")
    for i in range(frames):
        update(i / max(1, frames - 1) if frames > 1 else float(spec.get("at", 0.2)))
        sc.render.filepath = tmp
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(tmp)
        w, h = img.size
        px = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
        bpy.data.images.remove(img)
        np.save(os.path.join(fdir, f"{i:03d}.npy"), px.reshape(h, w, 4)[::-1].astype(np.float16))
    if os.path.isfile(tmp):
        os.remove(tmp)
    with open(os.path.join(fdir, "frames.json"), "w", encoding="utf-8") as fh:
        json.dump({"frames": frames, "spec_mtime": os.path.getmtime(spec["_path"])}, fh)
    # lit variants of a sim: the SAME bake rendered again with the key light moved (one simulation, several lightings)
    key = bpy.data.objects.get("KeySun")
    specs_dir = os.path.dirname(spec["_path"])
    for vf in sorted(os.listdir(specs_dir)) if key is not None else []:
        if not vf.endswith(".json"):
            continue
        vpath = os.path.join(specs_dir, vf)
        try:
            with open(vpath, encoding="utf-8") as fh:
                v = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        if v.get("recipe") != "lit_variant" or v.get("of") != name or v.get("light") not in LIGHTS:
            continue
        key.rotation_euler = [math.radians(r) for r in LIGHTS[v["light"]]]
        vname = vf[:-5]
        vdir = os.path.join(out_dir, vname)
        os.makedirs(vdir, exist_ok=True)
        for f in os.listdir(vdir):
            if f.endswith(".npy"):
                os.remove(os.path.join(vdir, f))
        for i in range(frames):
            update(i / max(1, frames - 1) if frames > 1 else float(spec.get("at", 0.2)))
            sc.render.filepath = tmp
            bpy.ops.render.render(write_still=True)
            img = bpy.data.images.load(tmp)
            w, h = img.size
            px = np.empty(w * h * 4, dtype=np.float32)
            img.pixels.foreach_get(px)
            bpy.data.images.remove(img)
            np.save(os.path.join(vdir, f"{i:03d}.npy"), px.reshape(h, w, 4)[::-1].astype(np.float16))
        with open(os.path.join(vdir, "frames.json"), "w", encoding="utf-8") as fh:
            json.dump({"frames": frames, "spec_mtime": os.path.getmtime(vpath), "of": name}, fh)
        LIT_DONE.add(vname)
    if os.path.isfile(tmp):
        os.remove(tmp)
    cache_root = os.path.join(out_dir, "_cache")  # Mantaflow bakes (smoke_sim / fire_sim) are not kept: gigabytes per run
    if os.path.isdir(cache_root):
        import shutil
        shutil.rmtree(cache_root, ignore_errors=True)
    return frames


def main():
    a = args()
    specs, out = os.path.abspath(a["specs"]), os.path.abspath(a["out"])
    os.makedirs(out, exist_ok=True)
    names = a["names"] or sorted(f[:-5] for f in os.listdir(specs) if f.endswith(".json"))
    results, errors = [], []
    for nm in names:
        path = os.path.join(specs, f"{nm}.json")
        if not os.path.isfile(path):
            errors.append(f"{nm}: no spec {path}")
            continue
        with open(path, encoding="utf-8") as fh:
            spec = json.load(fh)
        if spec.get("engine") != "fx":
            continue
        spec["_path"] = path
        meta = os.path.join(out, nm, "frames.json")
        fresh = False
        if os.path.isfile(meta):
            with open(meta, encoding="utf-8") as fh:
                m = json.load(fh)
            fresh = m.get("spec_mtime") == os.path.getmtime(path)
            # an import cached before the sheet slice (2026-10-24) holds ONE frame for a sheet spec: re-import it
            if spec.get("recipe") == "import" and int(spec.get("frames", 1) or 1) > 1 and m.get("frames") != int(spec["frames"]):
                fresh = False
            if spec.get("recipe") == "aura":  # the generator is code: a change to it re-renders every aura texture
                fresh = fresh and m.get("gen_mtime") == os.path.getmtime(os.path.join(os.path.dirname(os.path.abspath(__file__)), "aura.py"))
        t0 = time.time()
        if str(spec.get("recipe", "")).startswith("gpu_"):  # simulated + rendered on the GPU by kit/vfx/gpusim.py
            continue
        if spec.get("recipe") == "ink":  # drawn from a scene's traced drawings by kit/vfx/ink.py (numpy, no Blender)
            continue
        if spec.get("recipe") == "dissolve":  # a built texture breaking up, baked by kit/vfx/dissolve.py (numpy, no Blender)
            continue
        if spec.get("recipe") == "comp":  # a short 2D stack, baked by kit/vfx/comp.py (numpy, no Blender)
            continue
        if spec.get("recipe") == "liquid":  # a liquid solved and drawn by kit/vfx/liquid.py (numpy, no Blender)
            continue
        if spec.get("recipe") == "view_variant":
            continue  # a GPU sim's view (impostor) variant: kit/vfx/gpusim.py renders it
        if spec.get("recipe") == "lit_variant":
            parent_path = os.path.join(specs, f"{spec.get('of')}.json")
            if os.path.isfile(parent_path):
                with open(parent_path, encoding="utf-8") as fh:
                    if str(json.load(fh).get("recipe", "")).startswith("gpu_"):
                        continue  # a GPU sim's variant: gpusim.py renders it
            if nm in LIT_DONE or (fresh and not a["force"]):
                results.append({"name": nm, "frames": int(spec.get("frames", 1)), "seconds": 0, "rendered": nm in LIT_DONE})
                continue
            parent = spec.get("of")
            ppath = os.path.join(specs, f"{parent}.json")
            if not parent or not os.path.isfile(ppath):
                errors.append(f"{nm}: lit_variant of {parent!r}: no such sim spec")
                continue
            with open(ppath, encoding="utf-8") as fh:
                pspec = json.load(fh)
            pspec["_path"] = ppath
            try:
                render(parent, pspec, out)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{nm} (via {parent}): {type(e).__name__}: {e}")
                continue
            results.append({"name": nm, "frames": int(spec.get("frames", 1)), "seconds": round(time.time() - t0, 1), "rendered": True})
            continue
        try:
            n = int(spec.get("frames", 1)) if fresh and not a["force"] else render(nm, spec, out)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{nm}: {type(e).__name__}: {e}")
            continue
        results.append({"name": nm, "frames": n, "seconds": round(time.time() - t0, 1), "rendered": not fresh or a["force"]})
    rendered = [r["name"] for r in results if r["rendered"]]
    print(
        json.dumps(
            {
                "schema": 1,
                "status": "fail" if errors else "pass",
                "summary": "; ".join(errors) if errors else f"{len(results)} fx render(s) ({len(rendered)} rendered: {', '.join(rendered) or 'all fresh'})",
                "next_action": f"fix assets/textures/{errors[0]}" if errors else "none — proceed (kit/vfx/fxfinish.py packs the sheets)",
                "renders": [r for r in results if r["rendered"]],  # only what rendered: 180+ fresh entries made a 13 KB line
                "fresh": len(results) - len(rendered),
            }
        )
    )
    sys.exit(1 if errors else 0)


main()
