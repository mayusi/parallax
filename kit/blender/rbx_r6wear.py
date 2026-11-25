"""rbx_r6wear.py — R6 CLOTHES TO THE GAME'S STANDARD (LIMITATIONS_FIXES_V4 3D-X, 2.2 / 13.2: "< 4k quad-loft shell,
0.035 st rectangular clearance + 0.022 corner"; Sample Game cards 88sn / kj6f / qcet, the vault's 3d/clothes-topology).

The Hero coat and boots (1/10): round leg shells clipping the 1 x 2 x 1 blocks (789 of 4,800 points inside), 17.7k
triangles of decimated sculpt soup, 0 quads, open and non-manifold edges. The standard every R6 clothing piece is
held to, by numbers (Roblox's accessory specs: at most 4k triangles, one mesh, watertight, "use quads whenever
possible"):

  r6_tris       at most TRI_BUDGET triangles (as the game counts them: a quad is two)
  r6_quads      at least QUAD_BAR of them in quads (rbx_quads: a modelled loop, never soup)
  r6_closed     watertight: no open edge, no edge three faces share
  r6_clearance  nothing of it nearer the block it is worn on than CORNER studs (the rounded corners' allowance) -
                its faces stand CLEARANCE off (an animated block pokes through a closer shell; a coincident one
                flickers)

    import rbx_r6wear as W
    W.shell(a, "Shirt", "cloth", on="Torso", group="shirt")       # a quad-loft shell to the standard
    a.r6_wear("shirt", on="Torso")                                 # the build holds the group to it

The blocks stand in the R6 rig's own frame (studs, y up, -z front, the feet at y = 0 - rbx_garment's frame):
the torso 2 x 2 x 1 centred at (0, 3, 0), each arm 1 x 2 x 1 at x -/+1.5, each leg 1 x 2 x 1 at x -/+0.5, y 1.
Pure numpy above `shell` (unit-tested: kit/test/python/test_r6wear.py)."""

import math

import numpy as np

TRI_BUDGET = 4000     # Roblox: a rigid or layered accessory, at most 4k triangles
QUAD_BAR = 0.85       # of its triangles in quads
CLEARANCE = 0.035     # studs a shell's inner faces stand off its block
CORNER = 0.022        # studs: nearer than this anywhere (its rounded corners come closest) is a poke
THICKNESS = 0.02      # studs of wall (5.6 mm at 280 mm a stud: cloth with a lining)

BLOCKS = {   # name -> (centre, half size), studs, the R6 rig's frame
    "Torso": ((0.0, 3.0, 0.0), (1.0, 1.0, 0.5)),
    "LeftArm": ((-1.5, 3.0, 0.0), (0.5, 1.0, 0.5)),
    "RightArm": ((1.5, 3.0, 0.0), (0.5, 1.0, 0.5)),
    "LeftLeg": ((-0.5, 1.0, 0.0), (0.5, 1.0, 0.5)),
    "RightLeg": ((0.5, 1.0, 0.0), (0.5, 1.0, 0.5)),
}


def block(on):
    if on not in BLOCKS:
        raise ValueError(f"r6 wear: on={on!r} - one of {', '.join(BLOCKS)}")
    c, h = BLOCKS[on]
    return np.array(c, float), np.array(h, float)


def box_distance(points, on):
    """signed distance of each point from the block's box (studs; negative inside)"""
    c, h = block(on)
    q = np.abs(np.asarray(points, float).reshape(-1, 3) - c) - h
    outside = np.linalg.norm(np.maximum(q, 0.0), axis=1)
    inside = np.minimum(q.max(axis=1), 0.0)
    return outside + inside


def corner_radius(clearance=CLEARANCE, corner=CORNER):
    """the inner profile's corner radius that brings its corners to `corner` off the block's edge while its faces
    stand `clearance` off: the arc's centre (clearance - r) in from each face, its point on the diagonal
    sqrt(2) (clearance - r) + r from the block's edge"""
    r = (math.sqrt(2.0) * clearance - corner) / (math.sqrt(2.0) - 1.0)
    return max(0.0, min(r, clearance + 0.5))


def ring(hx, hz, r, nx, nz, nc):
    """a rounded rectangle (half sizes hx, hz, corner radius r) as points round it, counter-clockwise seen from
    above (+x toward -z... the angle in the x-z plane rising), each corner's arc in nc steps, each straight run along
    x in nx and along z in nz -> [(x, z)]. The same counts on every ring of a loft: its quads line up."""
    r = min(r, hx, hz)
    ax, az = hx - r, hz - r
    centres = [(ax, az), (-ax, az), (-ax, -az), (ax, -az)]
    steps = [nx, nz, nx, nz]   # (from the +x+z corner's arc end the run goes along x, then along z ...)
    pts = []
    for k, (cx, cz) in enumerate(centres):
        a0 = k * math.pi / 2
        for s in range(nc):
            a = a0 + (math.pi / 2) * s / nc
            pts.append((cx + r * math.cos(a), cz + r * math.sin(a)))
        a1 = a0 + math.pi / 2
        end = (cx + r * math.cos(a1), cz + r * math.sin(a1))
        ncx, ncz = centres[(k + 1) % 4]
        nxt = (ncx + r * math.cos(a1), ncz + r * math.sin(a1))
        for s in range(steps[k]):
            t = s / steps[k]
            pts.append((end[0] + (nxt[0] - end[0]) * t, end[1] + (nxt[1] - end[1]) * t))
    return pts


def loft(on, y0, y1, flare=None, clearance=CLEARANCE, corner=CORNER, thickness=THICKNESS, edge=0.14):
    """a closed QUAD shell round a block from height y0 to y1 (studs, the rig's frame): an inner wall standing
    `clearance` off the block (its corners `corner` off), an outer wall `thickness` beyond, both rims closed with
    quads, its quads about `edge` studs a side. flare=[(y, studs), ...]: more room at those heights (a coat flaring
    below the waist; linear between, the ends' values beyond) -> (verts [(x, y, z)], faces [quads])"""
    c, h = block(on)
    r = corner_radius(clearance, corner)
    nx = max(1, round(2 * (h[0] + clearance - r) / edge))
    nz = max(1, round(2 * (h[2] + clearance - r) / edge))
    nc = max(2, round((math.pi / 2) * (r + clearance) / edge) + 1)
    n_rows = max(2, round(abs(y1 - y0) / edge) + 1)
    ys = [y0 + (y1 - y0) * i / (n_rows - 1) for i in range(n_rows)]
    fl = sorted(flare or [])

    def extra(y):
        if not fl:
            return 0.0
        if y <= fl[0][0]:
            return fl[0][1]
        if y >= fl[-1][0]:
            return fl[-1][1]
        for (ya, ea), (yb, eb) in zip(fl, fl[1:]):
            if ya <= y <= yb:
                return ea + (eb - ea) * (y - ya) / max(yb - ya, 1e-9)
        return 0.0
    rings = []
    for wall in (0.0, thickness):
        rw = []
        for y in ys:
            e = extra(y)
            pts = ring(h[0] + clearance + e + wall, h[2] + clearance + e + wall, r + wall + e, nx, nz, nc)
            rw.append([(c[0] + x, y, c[2] + z) for x, z in pts])
        rings.append(rw)
    m = len(rings[0][0])
    verts, faces = [], []
    for rw in rings:
        for row in rw:
            verts += row
    inner = lambda i, j: i * m + j % m                                       # noqa: E731
    outer = lambda i, j: n_rows * m + i * m + j % m                          # noqa: E731
    for i in range(n_rows - 1):
        for j in range(m):
            faces.append((outer(i, j), outer(i + 1, j), outer(i + 1, j + 1), outer(i, j + 1)))   # outward
            faces.append((inner(i, j), inner(i, j + 1), inner(i + 1, j + 1), inner(i + 1, j)))   # toward the block
    for j in range(m):   # the rims: the bottom (i = 0) and the top (i = last), inner to outer
        faces.append((inner(0, j), outer(0, j), outer(0, j + 1), inner(0, j + 1)))
        t = n_rows - 1
        faces.append((inner(t, j), inner(t, j + 1), outer(t, j + 1), outer(t, j)))
    return verts, faces


def edges_open(faces):
    """-> (open edges, edges three or more faces share)"""
    count = {}
    for f in faces:
        for k in range(len(f)):
            e = tuple(sorted((f[k], f[(k + 1) % len(f)])))
            count[e] = count.get(e, 0) + 1
    return sum(1 for v in count.values() if v == 1), sum(1 for v in count.values() if v > 2)


def judge(verts, faces, on, samples=None):
    """the standard, measured -> {tris, quad_share, open_edges, pinched_edges, nearest, inside, ok: {...}}.
    samples: extra points of the surface (a face's own middle can cut a corner its corners keep clear of)"""
    import rbx_quads  # noqa: PLC0415

    co = np.asarray(verts, float).reshape(-1, 3)
    share, tris = rbx_quads.polygon_share([list(f) for f in faces], co)
    open_, pinched = edges_open(faces)
    pts = co if samples is None else np.vstack([co, np.asarray(samples, float).reshape(-1, 3)])
    d = box_distance(pts, on)
    facts = {"on": on, "tris": tris, "quad_share": round(share, 4), "open_edges": open_, "pinched_edges": pinched,
             "nearest": round(float(d.min()), 4) if len(d) else None,
             "inside": int((d < 0).sum()), "points": int(len(d))}
    facts["ok"] = {"r6_tris": tris <= TRI_BUDGET, "r6_quads": share >= QUAD_BAR,
                   "r6_closed": open_ == 0 and pinched == 0,
                   "r6_clearance": bool(len(d)) and float(d.min()) >= CORNER - 1e-4}
    return facts


def face_middles(verts, faces):
    co = np.asarray(verts, float).reshape(-1, 3)
    return np.array([co[list(f)].mean(axis=0) for f in faces]) if faces else np.zeros((0, 3))


def shell(a, name, mat, on="Torso", y0=None, y1=None, flare=None, group="main", **kw):
    """a quad-loft SHELL to the standard (loft above) round an R6 block, as a part: y0 / y1 default to the block's
    own bottom and top -> the part"""
    c, h = block(on)
    y0 = c[1] - h[1] if y0 is None else y0
    y1 = c[1] + h[1] if y1 is None else y1
    verts, faces = loft(on, y0, y1, flare=flare, **kw)
    return a.mesh(name, verts, faces, mat, group=group)
