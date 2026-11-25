"""rbx_ivy.py — English ivy (Hedera helix) GROWN up a wall from its botany, not typed (the owner 2026-10-17: "make
realistic vines very realistic"; graveyard G3: foliage typed from words never reaches the bar). Pure numpy.

grow(width, height, seed=, ...) -> {"stems": [{"pts": (n, 2) mm on the wall, "r": (n,) mm}], "leaves": [...]}

The plant: roots at the wall's foot; every tip climbs one INTERNODE a step (21 mm: the kit's dims, a cultivar's
measure) — drawn up (light), wandering (slow noise), pushed off crowded wall (a density grid: stems fan out across
bare wall, as the photographed ivy does) — and branches now and then. A stem's thickness follows the pipe model:
the tips it feeds (r = r_tip * n^0.5, a mature trunk to its sourced 40-60 mm only after decades — this wall's ~25).
Every node carries ONE leaf (alternate sides): a blade 40-120 mm long (Flora of Victoria: "4-12 cm long, 4-7 cm
wide"), its petiole about as long as the blade (Smithsonian: "petioles about as long as the blade"; the flora
2-10 cm) holding it off the wall, the blade facing out to the light with its tip down, shingled over the leaves
below. Old wood near the roots has dropped most of its leaves (a wall ivy's base is bare stems).
"""

import numpy as np

INTERNODE = 21.0                 # mm (dims: english ivy hedera helix internode, grade C)
BLADE = (40.0, 120.0)            # mm, juvenile blade length (dims, Flora of Victoria)
ASPECT = (40.0 / 120.0, 70.0 / 40.0)   # width / length bounds (4-7 cm wide on 4-12 cm long)
PETIOLE_K = (0.55, 1.1)          # petiole / blade (Smithsonian: about as long as the blade; flora 2-10 cm)
R_TIP = 1.4                      # mm, a growing tip's stem radius
R_MAX = 26.0                     # mm, this wall's oldest trunk (sourced mature 40-60 mm diameter: decades older)


def _noise1(rng, n, smooth=12):
    """a slow random wander (n,) in -1..1: white noise smoothed over `smooth` steps"""
    x = rng.normal(size=n + 4 * smooth)
    k = np.exp(-0.5 * (np.arange(-2 * smooth, 2 * smooth + 1) / smooth) ** 2)
    y = np.convolve(x, k / k.sum(), mode="same")[2 * smooth: 2 * smooth + n]
    return y / (np.abs(y).max() + 1e-9)


def grow(width, height, seed=1, roots=3, steps=150, branch_p=0.045, max_tips=60, cell=60.0, up=0.55, wander=0.55,
         crowd=0.9, overhang=0.0):
    """the ivy's stems on a wall `width` x `height` mm (x right, y up, 0,0 its lower left) -> stems + leaves"""
    rng = np.random.default_rng(seed)
    gx, gy = int(np.ceil(width / cell)), int(np.ceil(height / cell))
    dens = np.zeros((gy + 2, gx + 2))
    stems = []   # each: dict(pts list, parent, born step)
    tips = []    # (stem index, dir angle, noise array, age)
    for k in range(roots):
        x = width * (k + 0.5 + rng.uniform(-0.25, 0.25)) / roots
        stems.append({"pts": [np.array([x, 0.0])], "parent": None, "at": 0})
        tips.append([len(stems) - 1, np.radians(90 + rng.uniform(-25, 25)), _noise1(rng, steps * 2), 0,
                     steps * 2])
    for step in range(steps):
        new = []
        for t in tips:
            si, ang, nz, age, life = t
            if age >= life:
                continue   # (this shoot stops here: every tip its own lifespan — a ragged edge, never a rectangle)
            p = stems[si]["pts"][-1]
            # crowding: the density gradient pushes the tip toward bare wall
            ix, iy = int(np.clip(p[0] / cell, 0, gx - 1)) + 1, int(np.clip(p[1] / cell, 0, gy - 1)) + 1
            gxd = dens[iy, ix + 1] - dens[iy, ix - 1]
            gyd = dens[iy + 1, ix] - dens[iy - 1, ix]
            d = np.array([np.cos(ang), np.sin(ang)])
            d = d + up * np.array([0.0, 1.0]) + wander * nz[min(age, len(nz) - 1)] * np.array([-d[1], d[0]]) \
                - crowd * np.array([gxd, gyd]) / (1.0 + dens[iy, ix])
            d /= max(np.linalg.norm(d), 1e-9)
            q = p + d * INTERNODE
            if q[0] < 0 or q[0] > width or q[1] > height + overhang:
                continue   # (off the wall: this tip stops; the top edge is the wall's)
            q[1] = max(q[1], 0.0)
            stems[si]["pts"].append(q)
            dens[int(np.clip(q[1] / cell, 0, gy - 1)) + 1, int(np.clip(q[0] / cell, 0, gx - 1)) + 1] += 1.0
            t[1], t[3] = np.arctan2(d[1], d[0]), age + 1
            new.append(t)
            if len(tips) + len(new) < max_tips and rng.random() < branch_p and age > 3:
                side = rng.choice([-1, 1])
                a2 = t[1] + side * np.radians(rng.uniform(30, 65))
                stems.append({"pts": [q.copy()], "parent": si, "at": len(stems[si]["pts"]) - 1})
                new.append([len(stems) - 1, a2, _noise1(rng, steps * 2), 0, int(rng.uniform(25, 110))])
        tips = new
        if not tips:
            break
    # the pipe model: each node's radius from the tips downstream of it
    n_tips = [np.ones(len(s["pts"])) for s in stems]
    for si in range(len(stems) - 1, -1, -1):   # (children are made after their parents: walk back)
        s = stems[si]
        cum = np.cumsum(n_tips[si][::-1])[::-1]   # (tips beyond each node on this stem, itself counted per node)
        n_tips[si] = cum
        if s["parent"] is not None:
            n_tips[s["parent"]][: s["at"] + 1] += cum[0] if len(cum) else 0
    out = []
    for si, s in enumerate(stems):
        pts = np.array(s["pts"])
        if len(pts) < 2:
            continue
        nn = n_tips[si] / INTERNODE * 0 + n_tips[si]
        r = np.clip(R_TIP * (nn / 6.0) ** 0.5, R_TIP, R_MAX)
        out.append({"pts": pts, "r": r, "parent": s["parent"]})
    leaves = place_leaves(out, rng, height)
    return {"stems": out, "leaves": leaves, "width": width, "height": height}


def place_leaves(stems, rng, height):
    """one leaf a node, alternate sides; old thick wood near the roots mostly bare"""
    leaves = []
    for s in stems:
        pts, r = s["pts"], s["r"]
        for i in range(1, len(pts)):
            # (bare old wood: a node's chance of a leaf falls as its stem thickens)
            keep = np.clip(1.15 - (r[i] - R_TIP) / 9.0, 0.08, 1.0)
            if rng.random() > keep:
                continue
            d = pts[i] - pts[i - 1]
            d /= max(np.linalg.norm(d), 1e-9)
            side = 1 if i % 2 else -1
            # younger leaves (near a tip) smaller; a size spread from the sourced range
            young = np.clip((len(pts) - i) / 12.0, 0.35, 1.0)
            L = rng.uniform(*BLADE) * (0.55 + 0.45 * young)
            pet = L * rng.uniform(*PETIOLE_K)
            # the petiole leaves the stem sideways and out from the wall, the blade hangs tip-down, turned a little
            lateral = np.array([-d[1], d[0]]) * side
            out_dir = lateral * 0.55 + np.array([0, -0.15])
            # every leaf its own pose (the first build: all the same tilt and tip-down — read as fish scales): rolled
            # about its normal, tilted 5-60 deg to the light, its tip swung, its petiole lifting it 30-100% out
            roll = np.radians(rng.normal(0, 14))
            leaves.append({"node": pts[i].copy(), "stem_r": float(r[i]), "length": float(L), "petiole": float(pet),
                           "lateral": out_dir / max(np.linalg.norm(out_dir), 1e-9), "lift": float(np.clip(rng.normal(0.75, 0.22), 0.3, 1.25)),
                           "roll": float(roll), "tilt": float(np.radians(rng.uniform(15, 45))),
                           "swing": float(rng.normal(0, 0.55)), "tone": float(rng.random()),
                           "leaf": int(rng.integers(0, 1 << 30))})
    return leaves
