"""VERTEX PAINT (the owner's method lists, 2026-11-13: "vertex colours", "vertex-painted blending"; the 3D methods
audit, stage S4).

A colour the artist gives the SURFACE itself, by where a point is: darker toward the ground, a warmer side, one
copy a shade off the next. In a game engine that is the mesh's vertex colours, multiplied into its texture.
Roblox shows a mesh's vertex colours on a part with a plain material or a TextureID - and, by the reports the kit
has (DevForum, 2025; not seen by the kit in Studio), NOT under a SurfaceAppearance, which is what the kit ships.
So a paint is laid twice, each where it is seen: MULTIPLIED INTO THE COLOUR MAP (what a SurfaceAppearance shows),
at every texel by the rule itself, and written into the mesh's vertex colours in the file (what a part shows that
is given the mesh without its maps). Pure numpy; no Blender."""

import numpy as np


def tint(points, color):
    """the paint at points of the surface -> (N, 3) 0..1. color: (r, g, b), one grey number, or a rule on the
    point (x, y, z in the model's frame, studs) giving either; 1 = the surface as it is, lower = darker"""
    pts = np.asarray(points, float).reshape(-1, 3)
    if callable(color):
        got = [color(tuple(p)) for p in pts]
        out = np.array([(g, g, g) if np.isscalar(g) else tuple(g)[:3] for g in got], float).reshape(-1, 3)
    else:
        one = (color, color, color) if np.isscalar(color) else tuple(color)[:3]
        out = np.tile(np.asarray(one, float), (len(pts), 1))
    return np.clip(out, 0.0, 1.0)


def to_srgb(x):
    """linear 0..1 -> sRGB 0..1 (an array)"""
    x = np.clip(np.asarray(x, float), 0.0, 1.0)
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def over(base, more):
    """two paints on the same surface: multiplied"""
    return np.asarray(base, float) * np.asarray(more, float)


def said(values):
    """a paint, in a word: its mean and how far it reaches -> {"mean": [r, g, b], "darkest", "lightest"}"""
    v = np.asarray(values, float).reshape(-1, 3)
    if not len(v):
        return {"mean": [1.0, 1.0, 1.0], "darkest": 1.0, "lightest": 1.0}
    grey = v.mean(axis=1)
    return {"mean": [round(float(c), 3) for c in v.mean(axis=0)], "darkest": round(float(grey.min()), 3),
            "lightest": round(float(grey.max()), 3)}


def read_problem(meant_mean, read_mean, tol=0.04):
    """the paint read back from the exported file against the paint the build wrote -> a sentence, or None.
    read_mean None: the file holds no vertex colours at all"""
    if read_mean is None:
        return "the paint is not in the file: it holds no vertex colours"
    far = float(np.abs(np.asarray(meant_mean, float) - np.asarray(read_mean, float)).max())
    if far > tol:
        return (f"the file's vertex colours are not the paint the build wrote (mean "
                f"{[round(float(c), 2) for c in read_mean]} against {[round(float(c), 2) for c in meant_mean]})")
    return None


CORNER_TOL = 0.06     # how far a corner's colour in the file may lie from the paint asked there (8-bit, sRGB)
CORNER_SHARE = 0.02   # more of the corners than this off: the file does not hold the paint


def corner_problem(off, tol=CORNER_TOL, share=CORNER_SHARE):
    """the file's vertex colours against the paint asked, corner by corner -> a sentence, or None. off: for each
    corner looked up, how far the nearest colour the file holds at its place lies from the one asked (0..1)"""
    off = np.asarray(off, float)
    if not len(off):
        return None
    bad = float((off > tol).mean())
    if bad <= share:
        return None
    return (f"the file's vertex colours are not the paint the script asks: {bad:.0%} of the corners looked up are "
            f"off by more than {tol:g} (the worst {float(off.max()):.2f})")
