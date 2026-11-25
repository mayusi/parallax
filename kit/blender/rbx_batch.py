"""WHAT A MODEL COSTS TO DRAW, PAST ITS TRIANGLES (the owner's method lists, 2026-11-13: "draw calls", "overdraw";
the 3D methods audit, stage O: "draw calls (per group)", "overdraw: missing").

DRAWS. In Roblox every group of a kit model is one MeshPart with its own mesh and its own maps: one draw each
(identical MeshParts are drawn together; two different groups never are). A group earns its draw when it MOVES
(a joint), when it is SEEN THROUGH (a cut-out, a fade, glass: its own mode), or when it needs a map of its own.
Solid groups that never move apart and share nothing but the model are draws a join would save.

OVERDRAW. A BLENDED surface (glass, a fade) is drawn OVER what is behind it: every layer a view crosses is the
same pixels painted again (panes behind panes, smoke sheets, veils). The cost is the number of blended faces that
FACE the eye along a line of sight (a back is culled, unless the part was given one) - counted here along rays
through the model from its six sides. A hard cut-out is not blended: it is sorted by depth and drawn once.
Pure numpy (the rays are the builder's); no Blender."""

import numpy as np

DRAWS_BAR = 4      # more solid, unmoving groups than this in one model: said
LAYERS_BAR = 4.0   # a view that crosses more see-through layers than this (its 95th percentile): said


def draws(groups):
    """a model's draws -> {"draws", "moving", "see_through", "solid": [names], "saved": draws a join would save}.
    groups: [{"name", "moves": bool, "see_through": bool}] (main first)"""
    moving = [g["name"] for g in groups if g.get("moves")]
    clear = [g["name"] for g in groups if g.get("see_through") and not g.get("moves")]
    solid = [g["name"] for g in groups if not g.get("moves") and not g.get("see_through")]
    return {"draws": len(groups), "moving": moving, "see_through": clear, "solid": solid,
            "saved": max(len(solid) - 1, 0)}


def draw_problem(found, bar=DRAWS_BAR):
    """too many solid groups that never move apart -> a sentence, or None"""
    if len(found["solid"]) <= bar:
        return None
    return (f"{len(found['solid'])} solid groups never move apart ({', '.join(found['solid'][:6])}"
            f"{', ...' if len(found['solid']) > 6 else ''}): each is its own draw and its own maps - as one group "
            f"they are one ({found['saved']} draws saved), unless a group needs a map to itself")


def layers(counts):
    """the see-through layers lines of sight cross -> {"rays": the rays that met any, "mean", "p95", "most"}.
    counts: for every ray sent, how many see-through surfaces it crossed (0 = it met none: not counted)"""
    c = np.asarray(counts, float)
    c = c[c > 0]
    if not len(c):
        return {"rays": 0, "mean": 0.0, "p95": 0.0, "most": 0}
    return {"rays": int(len(c)), "mean": round(float(c.mean()), 2), "p95": round(float(np.percentile(c, 95)), 2),
            "most": int(c.max())}


def overdraw_problem(found, bar=LAYERS_BAR):
    """a model whose see-through parts stack too deep -> a sentence, or None"""
    if found["p95"] <= bar:
        return None
    return (f"a line of sight crosses up to {found['most']} see-through layers ({found['p95']:g} at the 95th "
            f"percentile, {found['mean']:g} on average): each is painted over the last - fewer, larger cards; a "
            "solid core with see-through only at the outline; or a hard cut-out (it is sorted by depth, drawn once)")


def grid(lo, hi, axis, sign, n=24):
    """the rays of one view: an n x n grid over the model's box seen along `axis` (0, 1, 2) from the side `sign`
    (+1 / -1) -> (starts (n*n, 3), direction (3,), reach). Each ray starts just outside the box and runs
    through it."""
    lo, hi = np.asarray(lo, float), np.asarray(hi, float)
    size = np.maximum(hi - lo, 1e-9)
    others = [i for i in range(3) if i != axis]
    a = lo[others[0]] + (np.arange(n) + 0.5) / n * size[others[0]]
    b = lo[others[1]] + (np.arange(n) + 0.5) / n * size[others[1]]
    aa, bb = np.meshgrid(a, b, indexing="ij")
    starts = np.zeros((n * n, 3))
    starts[:, others[0]] = aa.ravel()
    starts[:, others[1]] = bb.ravel()
    pad = 0.01 * float(size.max())
    starts[:, axis] = (hi[axis] + pad) if sign > 0 else (lo[axis] - pad)
    direction = np.zeros(3)
    direction[axis] = -1.0 if sign > 0 else 1.0
    return starts, direction, float(size[axis] + 2 * pad)
