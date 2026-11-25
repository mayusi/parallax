"""meshes.py — effect meshes for Roblox VFX, generated headless in Blender from small JSON specs.

    blender -b --factory-startup --python-exit-code 2 -P kit/vfx/meshes.py -- --specs assets/effects/meshes
            --out build/vfxmeshes --registry assets/effects/_meshes.json [name ...]

Top Roblox VFX is built from custom meshes (shockwave domes, slash crescents, swirls, spike bursts, glyph rings)
with gradient/noise textures on Neon or ForceField materials, animated by size/colour/transparency over time.
This makes those meshes. Spec: assets/effects/meshes/<name>.json = {"type": ..., params}:

  dome      radius, height, segments=32, rings=10            hemisphere shell (shockwaves, shields). v: base->top
  sphere    radius, segments=24, rings=12                     closed ball (energy cores)
  ring      inner, outer, segments=48                         flat annulus (ground shockwaves). v: inner->outer
  torus     radius, tube, segments=48, sides=10               donut (halos, portals)
  shell     radius_bottom, radius_top, height, segments=32, twist=0   open tube wall (dust walls, beams, tornados)
  crescent  radius, width, arc=160, thickness=0, segments=32  slash arc ribbon, tapered tips. u: along the arc
  spiral    radius, height, turns=2, width, segments=96       rising helix ribbon (charge-ups, tornados)
  spikes    count, length, base, seed=1                       starburst of cones from the centre (impacts)
  glyph_ring inner, outer, glyphs=12, gap=0.3, seed=1          ring broken into rune-like blocks (magic circles)

All shells are double-sided (both faces built in: a runtime MeshPart can't be switched double-sided). Units are
studs at scale 1; Vfx `scale` multiplies them. Outputs: build/vfxmeshes/<name>.fbx (import in Studio, then
`lune run kit asset-id build/vfxmeshes/<name>.fbx <id>`) + <name>.obj (the VFX preview draws it). The registry
entry keeps the uploaded id; until there is one, the runtime shows `fallback` (a primitive) at the same size.
Prints one JSON line: {status, summary, next_action, meshes:[{name, tris, size, file}]}.
"""

import json
import math
import os
import random
import sys

import bmesh
import bpy
from mathutils import Matrix

FALLBACK = {
    "dome": "Ball",
    "sphere": "Ball",
    "ring": "Cylinder",
    "torus": "Cylinder",
    "shell": "Cylinder",
    "crescent": "Block",
    "spiral": "Cylinder",
    "spikes": "Ball",
    "glyph_ring": "Cylinder",
}
MAX_TRIS = 10000


def args():
    a = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    out = {"names": []}
    i = 0
    while i < len(a):
        if a[i].startswith("--"):
            out[a[i][2:]] = a[i + 1]
            i += 2
        else:
            out["names"].append(a[i])
            i += 1
    return out


class Geo:
    """Roblox-space vertices, faces and per-corner UVs."""

    def __init__(self):
        self.v, self.f, self.uv = [], [], []

    def vert(self, p):
        self.v.append(tuple(p))
        return len(self.v) - 1

    def face(self, idx, uvs):
        self.f.append(list(idx))
        self.uv.append(list(uvs))

    def grid(self, rows, cols, pos, uv, wrap_u=True):
        """rows x cols lattice: pos(i, j) -> xyz, uv(i, j) -> (u, v). Wraps around in j when wrap_u."""
        ids = [[self.vert(pos(i, j)) for j in range(cols)] for i in range(rows)]
        span = cols if wrap_u else cols - 1
        for i in range(rows - 1):
            for j in range(span):
                j2 = (j + 1) % cols
                uj2 = j + 1  # UVs never wrap: the seam gets u=1
                self.face(
                    [ids[i][j], ids[i][j2], ids[i + 1][j2], ids[i + 1][j]],
                    [uv(i, j), uv(i, uj2), uv(i + 1, uj2), uv(i + 1, j)],
                )

    def double_sided(self):
        n = len(self.f)
        for k in range(n):
            self.f.append(list(reversed(self.f[k])))
            self.uv.append(list(reversed(self.uv[k])))


def build(spec):
    t = spec.get("type")
    g = Geo()
    tau = 2 * math.pi
    if t == "dome":
        r, h = spec.get("radius", 1), spec.get("height", spec.get("radius", 1))
        seg, rings = spec.get("segments", 32), spec.get("rings", 10)
        g.grid(
            rings + 1,
            seg,
            lambda i, j: (
                math.cos(tau * j / seg) * r * math.cos(math.pi / 2 * i / rings),
                h * math.sin(math.pi / 2 * i / rings),
                math.sin(tau * j / seg) * r * math.cos(math.pi / 2 * i / rings),
            ),
            lambda i, j: (j / seg, i / rings),
        )
        g.double_sided()
    elif t == "sphere":
        r, seg, rings = spec.get("radius", 1), spec.get("segments", 24), spec.get("rings", 12)
        # inner rings as a grid, then a triangle fan to each pole (a grid row AT a pole collapses to one point)
        first = len(g.v)
        g.grid(
            rings - 1,
            seg,
            lambda i, j: (
                math.cos(tau * j / seg) * r * math.sin(math.pi * (i + 1) / rings),
                -r * math.cos(math.pi * (i + 1) / rings),
                math.sin(tau * j / seg) * r * math.sin(math.pi * (i + 1) / rings),
            ),
            lambda i, j: (j / seg, (i + 1) / rings),
        )
        south, north = g.vert((0, -r, 0)), g.vert((0, r, 0))
        top = first + (rings - 2) * seg
        for j in range(seg):
            j2 = (j + 1) % seg
            g.face([south, first + j2, first + j], [(j / seg + 0.5 / seg, 0), ((j + 1) / seg, 1 / rings), (j / seg, 1 / rings)])
            g.face([north, top + j, top + j2], [(j / seg + 0.5 / seg, 1), (j / seg, 1 - 1 / rings), ((j + 1) / seg, 1 - 1 / rings)])
    elif t == "ring":
        ri, ro, seg = spec.get("inner", 0.8), spec.get("outer", 1), spec.get("segments", 48)
        g.grid(
            2,
            seg,
            lambda i, j: (math.cos(tau * j / seg) * (ri if i == 0 else ro), 0, math.sin(tau * j / seg) * (ri if i == 0 else ro)),
            lambda i, j: (j / seg, i),
        )
        g.double_sided()
    elif t == "torus":
        R, rt = spec.get("radius", 1), spec.get("tube", 0.15)
        seg, sides = spec.get("segments", 48), spec.get("sides", 10)
        g.grid(
            sides + 1,
            seg,
            lambda i, j: (
                math.cos(tau * j / seg) * (R + rt * math.cos(tau * i / sides)),
                rt * math.sin(tau * i / sides),
                math.sin(tau * j / seg) * (R + rt * math.cos(tau * i / sides)),
            ),
            lambda i, j: (j / seg, i / sides),
        )
    elif t == "shell":
        rb, rt = spec.get("radius_bottom", 1), spec.get("radius_top", spec.get("radius_bottom", 1))
        h, seg = spec.get("height", 2), spec.get("segments", 32)
        twist = math.radians(spec.get("twist", 0))
        rows = max(2, int(spec.get("rows", 6)))
        g.grid(
            rows,
            seg,
            lambda i, j: (
                math.cos(tau * j / seg + twist * i / (rows - 1)) * (rb + (rt - rb) * i / (rows - 1)),
                h * i / (rows - 1),
                math.sin(tau * j / seg + twist * i / (rows - 1)) * (rb + (rt - rb) * i / (rows - 1)),
            ),
            lambda i, j: (j / seg, i / (rows - 1)),
        )
        g.double_sided()
    elif t == "crescent":
        r, w = spec.get("radius", 3), spec.get("width", 0.8)
        arc, seg = math.radians(spec.get("arc", 160)), spec.get("segments", 32)

        def pos(i, j):
            a = -arc / 2 + arc * j / seg
            taper = math.sin(math.pi * j / seg) ** 0.6  # pointed tips
            rr = r + (w * taper if i == 1 else 0)
            return (math.sin(a) * rr, 0, -math.cos(a) * rr)

        g.grid(2, seg + 1, pos, lambda i, j: (j / seg, i), wrap_u=False)
        g.double_sided()
    elif t == "spiral":
        r, h = spec.get("radius", 1.5), spec.get("height", 4)
        turns, w, seg = spec.get("turns", 2), spec.get("width", 0.5), spec.get("segments", 96)

        def pos(i, j):
            a = tau * turns * j / seg
            y = h * j / seg + (w if i == 1 else 0)
            return (math.cos(a) * r, y, math.sin(a) * r)

        g.grid(2, seg + 1, pos, lambda i, j: (j / seg, i), wrap_u=False)
        g.double_sided()
    elif t == "spikes":
        rnd = random.Random(spec.get("seed", 1))
        count, length, base = spec.get("count", 12), spec.get("length", 3), spec.get("base", 0.25)
        sides = 5
        for k in range(count):
            # even-ish directions on a sphere (golden spiral) + jitter, upper hemisphere biased
            y = 1 - (k + 0.5) / count * 1.3
            rr = math.sqrt(max(0.0, 1 - min(1, y) ** 2))
            phi = k * 2.399963 + rnd.uniform(-0.3, 0.3)
            d = (math.cos(phi) * rr, max(-0.3, y), math.sin(phi) * rr)
            n = math.sqrt(sum(c * c for c in d)) or 1
            d = tuple(c / n for c in d)
            L = length * rnd.uniform(0.6, 1.0)
            a = (1.0, 0, 0) if abs(d[0]) < 0.9 else (0, 1.0, 0)
            u = (d[1] * a[2] - d[2] * a[1], d[2] * a[0] - d[0] * a[2], d[0] * a[1] - d[1] * a[0])
            un = math.sqrt(sum(c * c for c in u))
            u = tuple(c / un for c in u)
            w = (d[1] * u[2] - d[2] * u[1], d[2] * u[0] - d[0] * u[2], d[0] * u[1] - d[1] * u[0])
            ring = [
                g.vert(tuple(base * (math.cos(tau * s / sides) * u[c] + math.sin(tau * s / sides) * w[c]) for c in range(3)))
                for s in range(sides)
            ]
            tip = g.vert(tuple(d[c] * L for c in range(3)))
            for s in range(sides):
                g.face([ring[s], ring[(s + 1) % sides], tip], [(s / sides, 0), ((s + 1) / sides, 0), (s / sides + 0.5 / sides, 1)])
            g.face(list(reversed(ring)), [(0.5, 0)] * sides)
    elif t == "glyph_ring":
        rnd = random.Random(spec.get("seed", 1))
        ri, ro = spec.get("inner", 3), spec.get("outer", 3.6)
        glyphs, gap = spec.get("glyphs", 12), spec.get("gap", 0.3)
        per = tau / glyphs
        for k in range(glyphs):
            a0 = k * per + per * gap / 2
            a1 = (k + 1) * per - per * gap / 2
            # each glyph: 2-3 stacked blocks of random radial extent (reads as runes at a distance)
            cuts = sorted(rnd.uniform(0.2, 0.8) for _ in range(rnd.randint(1, 2)))
            bands = list(zip([0.0] + cuts, cuts + [1.0]))
            for bi, (b0, b1) in enumerate(bands):
                if bi % 2 == 1 and len(bands) > 2:
                    continue
                r0, r1 = ri + (ro - ri) * b0, ri + (ro - ri) * b1
                steps = 4
                for s in range(steps):
                    t0 = a0 + (a1 - a0) * s / steps
                    t1 = a0 + (a1 - a0) * (s + 1) / steps
                    p = [
                        g.vert((math.cos(t0) * r0, 0, math.sin(t0) * r0)),
                        g.vert((math.cos(t1) * r0, 0, math.sin(t1) * r0)),
                        g.vert((math.cos(t1) * r1, 0, math.sin(t1) * r1)),
                        g.vert((math.cos(t0) * r1, 0, math.sin(t0) * r1)),
                    ]
                    u0, u1 = t0 / tau, t1 / tau
                    g.face(p, [(u0, b0), (u1, b0), (u1, b1), (u0, b1)])
        g.double_sided()
    else:
        raise ValueError(f'unknown type "{t}" (dome sphere ring torus shell crescent spiral spikes glyph_ring)')
    return g


def to_blender(name, g):
    bm = bmesh.new()
    vs = [bm.verts.new((x, -z, y)) for x, y, z in g.v]  # Roblox (x, y, z) -> Blender (x, -z, y)
    uvl = bm.loops.layers.uv.new("UVMap")
    for face, uvs in zip(g.f, g.uv):
        try:
            f = bm.faces.new([vs[i] for i in face])
        except ValueError:  # a face bmesh rejects (repeated vertices) — generators avoid these; skip defensively
            continue
        for loop, uv in zip(f.loops, uvs):
            loop[uvl].uv = uv
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def write_obj(path, g):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("# kit vfx mesh (Roblox space, studs)\n")
        for x, y, z in g.v:
            fh.write(f"v {x:.4f} {y:.4f} {z:.4f}\n")
        for f in g.f:
            fh.write("f " + " ".join(str(i + 1) for i in f) + "\n")


def main():
    a = args()
    specs, out, registry = a["specs"], a["out"], a["registry"]
    os.makedirs(out, exist_ok=True)
    names = a["names"] or sorted(f[:-5] for f in os.listdir(specs) if f.endswith(".json"))
    reg = {}
    if os.path.isfile(registry):
        with open(registry, encoding="utf-8") as fh:
            reg = json.load(fh)
    results, errors = [], []
    for n in names:
        bpy.ops.wm.read_homefile(use_empty=True)
        try:
            with open(os.path.join(specs, f"{n}.json"), encoding="utf-8") as fh:
                spec = json.load(fh)
            g = build(spec)
        except Exception as e:  # noqa: BLE001 — every spec error becomes a readable gate message
            errors.append(f"{n}: {e}")
            continue
        tris = sum(len(f) - 2 for f in g.f)
        if tris > MAX_TRIS:
            errors.append(f"{n}: {tris} tris > {MAX_TRIS} — lower segments/rings")
        xs, ys, zs = zip(*g.v)
        size = [round(max(xs) - min(xs), 3), round(max(ys) - min(ys), 3), round(max(zs) - min(zs), 3)]
        size = [max(s, 0.05) for s in size]  # flat meshes still need a size Roblox accepts
        obj = to_blender(n, g)
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        fbx = os.path.join(out, f"{n}.fbx")
        # Roblox's mesh import turns an FBX 180 deg about Y (measured with the calibration mesh): pre-turn it
        obj.data.transform(Matrix.Rotation(math.pi, 4, "Z"))
        bpy.ops.export_scene.fbx(
            filepath=fbx,
            use_selection=True,
            axis_forward="-Z",
            axis_up="Y",
            apply_unit_scale=True,
            apply_scale_options="FBX_SCALE_UNITS",
            bake_anim=False,
            add_leaf_bones=False,
        )
        write_obj(os.path.join(out, f"{n}.obj"), g)
        entry = reg.get(n) if isinstance(reg.get(n), dict) else {}
        reg[n] = {
            "id": entry.get("id", ""),
            "fallback": FALLBACK.get(spec.get("type"), "Ball"),
            "size": size,
            "file": fbx.replace("\\", "/"),
        }
        results.append({"name": n, "tris": tris, "size": size, "file": fbx.replace("\\", "/")})
    reg["_help"] = (
        "kit-built effect meshes (assets/effects/meshes/*.json -> lune run kit vfx). Import <file> in Studio, then "
        "lune run kit asset-id <file> <id>. Until id is set the runtime shows `fallback` at `size`."
    )
    with open(registry, "w", encoding="utf-8") as fh:
        json.dump(dict(sorted(reg.items())), fh, indent=1)
        fh.write("\n")
    status = "fail" if errors else "pass"
    print(
        json.dumps(
            {
                "schema": 1,
                "status": status,
                "summary": "; ".join(errors) if errors else f"{len(results)} effect mesh(es) in {out}",
                "next_action": (f"fix assets/effects/meshes/{errors[0]}" if errors else "none — proceed"),
                "meshes": results,
            }
        )
    )
    sys.exit(1 if errors else 0)


main()
