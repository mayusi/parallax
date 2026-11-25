"""SURFACES THAT REPEAT, AND A STYLISED LOOK (the owner's method lists, 2026-11-13: "seamless / tileable",
"stylised shading"; the 3D methods audit, stage X: "seamless / tileable (object-space noise and tiling scans; no
author or checker)", "stylised shading (pbr=False skips the physical checks; no stylised model)").

A TILE is a square of one finish whose left edge meets its right and whose top meets its bottom, so it can cover a
wall, a floor or a whole terrain with no line where one copy ends: in Roblox a MaterialVariant (its ColorMap,
NormalMap, RoughnessMap, MetalnessMap and StudsPerTile). `tileable` makes a baked square repeat both ways; `steps`
says how well it does.

A STYLISED look in an engine with one lighting model (Roblox has no toon or cel shader) is PAINTED IN: the light
is drawn into the colour as a few flat tones by which way a surface faces, and the surface is then left matt and
flat so the engine's own light does not model it a second time. `ramp` is those tones.
Pure numpy; no Blender."""

import numpy as np

import rbx_trim

TILE_BAR = rbx_trim.TILE_SEEN      # a step of colour across a tile's wrap that is seen
TILE_SHARE = 0.0                   # any stretch of an edge that steps is a line at every joint


def tileable(img, blend=0.125):
    """a baked square made to REPEAT both ways: along U, then along V (each as rbx_trim.tileable_u: near an end
    the map is cross-faded into itself shifted by half its size - the middle is not touched). (H, W, C) -> new"""
    out = rbx_trim.tileable_u(np.asarray(img, float), blend)
    return np.swapaxes(rbx_trim.tileable_u(np.swapaxes(out, 0, 1), blend), 0, 1)


def steps(img):
    """how a map fails to repeat -> {"u": {"step", "share"}, "v": {...}} (rbx_trim.tile_step each way: the
    colour of its last columns against its first, and of its last rows against its first)"""
    img = np.asarray(img, float)
    return {"u": rbx_trim.tile_step(img), "v": rbx_trim.tile_step(np.swapaxes(img, 0, 1))}


def tile_problem(name, found, bar=TILE_BAR, share=TILE_SHARE):
    """a tile's map that does not repeat -> a sentence, or None. found: steps() of the map"""
    # (a step is "seen" by rbx_trim.tile_step's own bar: its share is the part of the edge over it. The 95th
    # percentile alone let a hard line on a twentieth of an edge through - the review)
    bad = [f"{'left to right' if k == 'u' else 'top to bottom'} (a step seen over {v['share']:.0%} of that edge, "
           f"{v['step'] * 255:.0f} of 255 at its 95th percentile)" for k, v in sorted(found.items())
           if v["share"] > share]
    if not bad:
        return None
    return f"{name} does not repeat {' and '.join(bad)}: laid side by side its copies show a line"


def unit_normals(px):
    """a normal map after a cross-fade: two normals blended are SHORTER than one - each texel's vector made unit
    again. px: (H, W, >=3) 0..1 (the map as stored: 0.5 = 0) -> a new array, the same shape"""
    out = np.array(px, float)
    v = out[..., :3] * 2.0 - 1.0
    length = np.linalg.norm(v, axis=-1, keepdims=True)
    v = np.where(length > 1e-6, v / np.maximum(length, 1e-6), np.array([0.0, 0.0, 1.0]))
    out[..., :3] = v * 0.5 + 0.5
    return out


def lit_over_shade(luma, tone, shade):
    """THE PAINTED LIGHT, READ OFF THE WRITTEN MAP: the colour map's brightness where the ramp is brightest over
    its brightness where the ramp is darkest -> the ratio (1.0 = no painted light at all), or None when the ramp
    has no two tones. luma, tone: the same shape; tone is the ramp the script asks (shade..1)."""
    luma, tone = np.asarray(luma, float).ravel(), np.asarray(tone, float).ravel()
    top = tone >= tone.max() - 0.02
    low = tone <= max(float(shade), float(tone.min())) + 0.02
    if tone.max() - tone.min() < 0.05 or not top.any() or not low.any():
        return None
    return float(np.median(luma[top]) / max(float(np.median(luma[low])), 1e-6))


def style_problem(group, ratio, shade):
    """the painted light missing from the map -> a sentence, or None. A shade of s should leave the lit tone
    about 1 / sRGB(s) times its shade; half of that (the kit's wear and occlusion lie over it) still passes."""
    if ratio is None:
        return None
    want = 1.0 / max(float(np.power(max(float(shade), 1e-3), 1 / 2.2)), 1e-3)
    if ratio >= 1.0 + 0.5 * (want - 1.0):
        return None
    return (f"{group}: asked stylised, and its colour map is {ratio:.2f} times as light where the painted light "
            f"falls as in its shade (about {want:.1f} asked): the light is not in the map")


def ramp(normals, light=(0.35, 1.0, 0.45), bands=3, shade=0.45):
    """THE PAINTED LIGHT: how light a surface is drawn by which way it faces -> (N,) in shade..1.
    normals: (N, 3) (the model's frame, y up; need not be unit); light: where the painted light comes FROM;
    bands: how many flat tones (2 = lit and shadow, 3 = lit, half, shadow; 0 = a smooth ramp); shade: the darkest
    tone (the surface's own colour times this)."""
    n = np.asarray(normals, float).reshape(-1, 3)
    n = n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-30)
    ell = np.asarray(light, float)
    ell = ell / max(float(np.linalg.norm(ell)), 1e-30)
    lit = np.clip((n @ ell + 1.0) / 2.0, 0.0, 1.0)          # (half-Lambert: the far side is not all one black)
    if bands and int(bands) >= 2:
        k = int(bands)
        lit = np.minimum(np.floor(lit * k), k - 1) / (k - 1)
    return float(shade) + (1.0 - float(shade)) * lit


def tones(values, tol=0.02):
    """how many tones a painted light holds -> the count of the steps of `tol` it lands on (a few flat tones: a
    few; a smooth ramp: dozens)"""
    v = np.asarray(values, float).ravel()
    if not len(v):
        return 0
    return int(len(np.unique(np.round(v / tol))))
