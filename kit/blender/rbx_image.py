"""rbx_image.py — the quality judge's IMAGE measurements, in plain numpy (no bpy): rbx_quality renders the views in
Blender and hands the pixels here, so every measurement runs — and is unit-tested — in plain python too.

    box(a, r)                  local mean over a (2r+1) square (integral image)
    grow(m, n, shrink=False)   n steps of 3x3 dilation / erosion
    creases(gray, mask)        crease pixels of a flat-lit cavity render (the outline itself does not count)
    see_through(mask)          share of the silhouette that is thin see-through slits
    texture_bands(lum, valid)  the albedo's band-pass contrast at three scales, measured only over `valid` pixels
    visible_texture(...)       per-pixel texture contrast a player can see + where it was measured
"""

import numpy as np

# the scales (px at the judge's 1024 px views) of the band-pass texture contrast: band 0 = pixel..2 px (render and
# bake noise, fibres a player never resolves in game), band 1 = 2..6 px (grain lines, chips, scratches), band 2 =
# 6..18 px (grain bands, grime patches, worn areas, stencils). A player sees bands 1 and 2.
TEXTURE_SCALES = (2, 6, 18)
SEEN_BANDS = (1, 2)


def box(a, r):
    """box blur of a 2-D array (integral image, edge-clamped): the local mean over a (2r+1) square"""
    p = np.pad(a, r + 1, mode="edge").cumsum(0).cumsum(1)
    k = 2 * r + 1
    return (p[k:, k:] - p[:-k, k:] - p[k:, :-k] + p[:-k, :-k])[: a.shape[0], : a.shape[1]] / (k * k)


def grow(m, n, shrink=False):
    """n steps of 8-neighbour (3x3 square) dilation, or erosion with shrink=True — the outside counts as background"""
    for _ in range(n):
        p = np.pad(m, 1, constant_values=False)
        acc = p[1:-1, 1:-1].copy()
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy or dx:
                    sh = p[1 + dy:p.shape[0] - 1 + dy, 1 + dx:p.shape[1] - 1 + dx]
                    acc = (acc & sh) if shrink else (acc | sh)
        m = acc
    return m


def creases(gray, mask, step=0.05, inset=3):
    """-> (crease pixels, the silhouette eroded by `inset` px): the gradient of a flat-lit cavity render above `step`,
    inside the eroded silhouette (the outline itself is not a crease). The inset is a 4-neighbour (cross) erosion —
    the definition the detail component had when the owner graded, kept exactly."""
    gx = np.abs(np.diff(gray, axis=1, append=gray[:, -1:]))
    gy = np.abs(np.diff(gray, axis=0, append=gray[-1:, :]))
    inner = mask.copy()
    for _ in range(inset):
        p = np.pad(inner, 1, constant_values=False)
        inner = inner & p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:]
    return ((gx + gy) > step) & inner, inner


def see_through(mask, size=256, slit_px=2):
    """share of the silhouette that is THIN see-through gaps: background enclosed by the object (not reachable from
    the frame's edge) in slits a few pixels wide — light between slats, boards that do not meet. Measured with the
    view's LONGER side at `size` px (every quality view frames the model by its longer side, so a slit's width means
    the same on every view and every render size), where a morphological OPENING with a square element (erode then
    dilate, both slit_px) keeps every opening wider than ~2 x slit_px exactly — rectangles keep their corners, so a
    window, a trigger guard or a handle loop leaves no false slit — and only the thinner slits remain. The resampling
    keeps a pixel solid only when ALL of it is solid: a slit one render pixel wide survives it (sampling every k-th
    pixel would drop most of them)."""
    h, w = mask.shape
    if w < 8 or h < 8:
        return 0.0
    scale = max(h, w) / float(size)
    rows = np.unique(np.floor(np.arange(max(1, int(round(h / scale)))) * scale).astype(int))
    cols = np.unique(np.floor(np.arange(max(1, int(round(w / scale)))) * scale).astype(int))
    if scale > 1:  # min-pool: a low-res pixel is solid only if its whole block is
        m = np.minimum.reduceat(np.minimum.reduceat(mask.astype(np.uint8), rows, axis=0), cols, axis=1) > 0
    else:
        m = mask.copy()
    if m.shape[0] < 4 or m.shape[1] < 4:
        return 0.0
    bg = ~m
    out = np.zeros_like(bg)
    out[0, :], out[-1, :], out[:, 0], out[:, -1] = bg[0, :], bg[-1, :], bg[:, 0], bg[:, -1]
    while True:  # flood the background in from the frame's edge
        grown = out | (bg & (np.roll(out, 1, 0) | np.roll(out, -1, 0) | np.roll(out, 1, 1) | np.roll(out, -1, 1)))
        if (grown == out).all():
            break
        out = grown
    holes = bg & ~out
    wide = grow(grow(holes, slit_px, shrink=True), slit_px)
    slits = holes & ~wide
    if scale > 1:  # the slit's TRUE area: the original picture's background pixels inside the low-res slit blocks
        # (a 1 px slit fills a whole 4 px block down there: counted there, a hairline read 4x its size)
        by = np.searchsorted(rows, np.arange(h), side="right") - 1
        bx = np.searchsorted(cols, np.arange(w), side="right") - 1
        return float((slits[by][:, bx] & ~mask).sum()) / max(1, int(mask.sum()))
    return float(slits.sum()) / max(1, int(m.sum()))


def texture_bands(lum, valid, scales=TEXTURE_SCALES):
    """the albedo's band-pass contrast at each scale, relative to the local brightness (dark wood counts like light
    wood): band i = mean over r_i - mean over r_i+1, where every mean takes ONLY `valid` pixels (normalised
    convolution) — a crease, a dark gap between boards or the background never leaks into the surface's own texture.
    -> (bands list, the pixels with enough valid support to be measured)"""
    v = valid.astype(np.float64)
    levels = [lum]
    for r in scales:
        levels.append(box(lum * v, r) / np.maximum(box(v, r), 1e-6))
    base = np.maximum(0.05, levels[-1])
    bands = [(levels[i] - levels[i + 1]) / base for i in range(len(scales))]
    return bands, valid & (box(v, scales[-1]) > 0.3)


def visible_texture(lum, inner, crease, pad=2):
    """-> (contrast map, measured pixels): the texture contrast a player SEES at each surface pixel (the seen bands
    combined), measured on crease-free surface (creases grown by `pad` px are left out: geometry is not texture)"""
    bands, ok = texture_bands(lum, inner & ~grow(crease, pad))
    c = np.sqrt(sum(bands[i] ** 2 for i in SEEN_BANDS))
    return c, ok
