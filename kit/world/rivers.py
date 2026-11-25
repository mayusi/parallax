"""rivers.py — `kit world rivers <hm.json>`: WATER in the valleys the rivers carved (AAA gap W6).

    python kit/world/rivers.py <heightmap.hm.json> [--share 0.012] [--wide 0.0025] [--out <png>]

The terrain's stream-power erosion carves the river valleys but leaves them dry. This reads the stored heights,
routes every cell's water downhill (D8: to its lowest neighbour), accumulates the drainage area, and paints the
cells where the most water gathers (the top `share` of cells, never on a cliff, never in the sea round the land)
as a new painted role "river" (kit world maps it to Roblox Water: the existing painter fills the beds); the very
biggest flows (`wide`) widen by one cell. Rewrites the heightmap's "roles" + "paint" in place (heights untouched)
and draws the river map. Running it again re-derives the rivers from the heights (idempotent). One JSON line.
"""

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from terrain import PAINT_MAX, paint_decode, paint_encode  # noqa: E402  (one character a cell: chr(48 + role))


def accumulate(h):
    """D8 flow accumulation: each cell passes its area (1 + what reached it) to its lowest lower neighbour"""
    nx, nz = h.shape
    order = np.argsort(h, axis=None)[::-1]  # (highest first: water runs down)
    acc = np.ones(nx * nz)
    flat = h.ravel()
    for idx in order:
        x, z = divmod(int(idx), nz)
        best, bh = -1, flat[idx]
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                if dx == 0 and dz == 0:
                    continue
                xx, zz = x + dx, z + dz
                if 0 <= xx < nx and 0 <= zz < nz:
                    j = xx * nz + zz
                    if flat[j] < bh:
                        best, bh = j, flat[j]
        if best >= 0:
            acc[best] += acc[idx]
    return acc.reshape(nx, nz)


def main(argv):
    if not argv:
        print(json.dumps({"status": "fail", "summary": "usage: rivers.py <heightmap.hm.json>", "next_action": "lune run kit world rivers <Name>"}))
        return 2
    path = argv[0]
    share = float(argv[argv.index("--share") + 1]) if "--share" in argv else 0.012
    wide = float(argv[argv.index("--wide") + 1]) if "--wide" in argv else 0.0025
    with open(path, encoding="utf-8") as fh:
        hm = json.load(fh)
    if not isinstance(hm.get("paint"), str) or not isinstance(hm.get("roles"), list):
        print(json.dumps({"status": "fail", "summary": f"{path} is not painted", "next_action": "paint it first: lune run kit world terrain <Name> (the painter)"}))
        return 1
    nx, nz = hm["nx"], hm["nz"]
    h = np.array(hm["heights"], float).reshape(nx, nz)
    roles = [r for r in hm["roles"] if r != "river"]
    old_river = hm["roles"].index("river") if "river" in hm["roles"] else None
    paint = paint_decode(hm["paint"], (nx, nz))
    if old_river is not None:
        # an earlier run: give its cells back to what the painter would see there (the meadow, the first role)
        paint[paint == old_river] = 0
        paint[paint > old_river] -= 1
    acc = accumulate(h)
    step = float(hm.get("step", 4))
    gx, gz = np.gradient(h, step)
    slope = np.degrees(np.arctan(np.hypot(gx, gz)))
    edge = np.zeros_like(h, bool)
    edge[:3, :], edge[-3:, :], edge[:, :3], edge[:, -3:] = True, True, True, True
    lim = np.quantile(acc, 1 - share)
    river = (acc >= lim) & (slope < 30) & ~edge
    if "cliff" in roles:
        river &= paint != roles.index("cliff")
    big = (acc >= np.quantile(acc, 1 - wide)) & river
    grown = big.copy()
    for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        grown |= np.roll(big, (dx, dz), axis=(0, 1))
    river |= grown & (slope < 30) & ~edge
    # specks (a pit that gathers water from its few neighbours) are stray puddles, not rivers: keep runs of 8+ cells
    from scipy.ndimage import label

    lab, n = label(river, structure=np.ones((3, 3), bool))
    sizes = np.bincount(lab.ravel())
    keep = sizes >= 8
    keep[0] = False
    river = keep[lab]
    if len(roles) >= PAINT_MAX:
        print(json.dumps({"status": "fail", "summary": f"the paint already has {PAINT_MAX} roles (one character each): no room for river", "next_action": "drop a role from the painter"}))
        return 1
    roles.append("river")
    paint[river] = len(roles) - 1
    hm["roles"] = roles
    hm["paint"] = paint_encode(paint)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(hm, fh)
    png = argv[argv.index("--out") + 1] if "--out" in argv else os.path.splitext(path)[0] + ".rivers.png"
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(6, 6), dpi=100)
        ax.imshow(h.T, cmap="terrain", origin="upper")
        ax.imshow(np.ma.masked_where(~river.T, river.T), cmap="winter", origin="upper", alpha=0.9)
        ax.set_title(f"rivers: {int(river.sum())} cells ({river.mean() * 100:.1f} % of the land)", fontsize=9)
        ax.axis("off")
        fig.savefig(png, bbox_inches="tight")
        plt.close(fig)
    except Exception:  # (the map is a convenience: the paint is the product)
        png = None
    print(json.dumps({
        "status": "pass",
        "summary": f"{int(river.sum())} river cells ({river.mean() * 100:.1f} % of the land, the top {share * 100:.1f} % of the drainage) painted as \"river\" in {path.replace(os.sep, '/')}",
        "next_action": f"LOOK at {png.replace(os.sep, '/')}; then lune run kit world (river -> Water)" if png else "lune run kit world",
        "cells": int(river.sum()),
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
