"""rbx_project.py — paint a model with its reference pictures, and cut markings out of them (decals).

    a.trace_match("m107_side")                    # the picture is registered to the model by its trace
    a.project("m107_side", view="side")           # its colours onto every surface the side view sees FIRST
    a.project("m107_top", view="top", mix=0.8)    # more pictures blend by how squarely a surface faces each
    a.project("relic_side", detail=1.0, bump=1.0) # a LIT picture: keep the materials, take only its fine structure
    a.decal("serial", "m107_side", box=(812, 240, 905, 262))        # one marking, at its measured place
    a.decal("logo", "m107_top", box=((10, 12), (90, 20), (88, 60), (8, 52)), view="top")  # 4 corners: straightened

How (camera projection baked into the map — what texture painters do with reference photos):
- per texel of a group's map, its world position, normal, part and material are baked (emission passes on the map's
  own UVs)
- per picture, the model's depth is rendered from the picture's camera: orthographic, along the view, framed the way
  reference_match / colour_match frame it — the model's silhouette box (without the trace's ignore= groups) IS the
  trace outline's box, and the trace's frame places that box in the picture's own pixels
- a texel takes the picture's colour where it is the first thing that camera sees (depth test: occluded faces get
  nothing), weighted by how squarely it faces the camera (|n.v| through a soft ramp: grazing faces fade out), inside the
  traced outline only; the outline's edge band (feather, picture pixels: a photo's edge pixels are half backdrop)
  takes its colour from just inside
- several pictures blend by weight x |n.v|^6 (the squarest view wins; a 45-degree edge takes both); the result mixes
  over the baked colour map (mix) AFTER the kit's wear / AO / grime — the picture's own light, wear and dirt are the
  real ones. Roughness and metal stay the material's.
- DETAIL mode (detail > 0): a lit picture's colour is its light's, not the object's — the texel keeps its material's
  colour, times 1 + 0.5 x detail x s (linear light), s = the picture's thin features of LOG luminance (top-hats: the
  light and big shadows drop out), normalised per picture and re-centred (each material keeps its mean); bump= puts
  them in the normal map too.
Which side a picture paints: a side picture with the front on the RIGHT shows the model's right side (+X), with the
front on the LEFT its left side (-X) (mirror=True paints the other side too, mirrored: lettering reads backwards
there); a top picture is seen from above; front / back pictures from in front / behind.
The arithmetic is plain numpy (no Blender: kit/test/python/test_project.py); the Blender side (helper bakes, the
depth / normal renders, the check seen from each view) imports bpy inside its functions.
"""

import hashlib
import json
import math
import os
import tempfile

import numpy as np

VIEWS = ("side", "top", "front", "back")
BLEND_POWER = 6  # views blend by w * |n.v|^6: at 0.9 vs 0.44 facing the squarer view takes ~99%
EXR_NAME = "kit_project"

# Blender space: x = Roblox x (right), y = Roblox -z (the FRONT), z = up. Per view and the side of the picture its
# front is on: (dir = from the model TO the camera, right = the picture's +x, up = the picture's up); right x up = dir.
_BASIS = {
    ("side", "right"): ((1, 0, 0), (0, 1, 0), (0, 0, 1)),  # the right side (+X): the front points right
    ("side", "left"): ((-1, 0, 0), (0, -1, 0), (0, 0, 1)),  # the left side (-X): the front points left
    ("top", "right"): ((0, 0, 1), (0, 1, 0), (-1, 0, 0)),  # from above, front right: the model's left side is up
    ("top", "left"): ((0, 0, 1), (0, -1, 0), (1, 0, 0)),  # from above, front left: its right side is up
    ("front", "right"): ((0, 1, 0), (-1, 0, 0), (0, 0, 1)),  # from in front: the model's right side on the left
    ("back", "right"): ((0, -1, 0), (1, 0, 0), (0, 0, 1)),  # from behind
}


# ---------------------------------------------------------------------------------------------- geometry (pure)
def basis(view, front="right"):
    """the camera of a picture: (dir, right, up) unit vectors in Blender space. A front / back picture is what the
    camera there sees whatever its trace's front flag says (that flag only turns the trace's own u)."""
    if view not in VIEWS:
        raise ValueError(f'view="{view}" — use one of {", ".join(VIEWS)}')
    key = (view, front if view in ("side", "top") else "right")
    return tuple(np.asarray(v, np.float64) for v in _BASIS[key])


def frame(trace):
    """where the trace's outline box sits in its picture -> (x0, y1, length_px, height_ratio): the box spans x0..x0+L
    and y1 - hr*L..y1 in the picture's own pixels (pixel k covers k..k+1)."""
    fr = trace.get("frame") or {}
    if not {"x0", "y1", "length_px"} <= set(fr):
        raise ValueError("this trace has no picture frame (made before frames, or rotated / straightened: the warp is "
                         "not a shift) — re-run kit trace on the picture without --rotate / --straighten")
    return float(fr["x0"]), float(fr["y1"]), float(fr["length_px"]), max(float(trace.get("height_ratio", 0.3)), 1e-4)


def to_picture(a, b, fr):
    """frame fractions (a 0..1 along the picture's x, b 0..1 up) -> picture coordinates (X right, Y down)"""
    x0, y1, L, hr = fr
    return x0 + np.asarray(a) * L, y1 - np.asarray(b) * hr * L


def from_picture(X, Y, fr):
    x0, y1, L, hr = fr
    return (np.asarray(X) - x0) / L, (y1 - np.asarray(Y)) / (hr * L)


def design_to_ab(u, h, front, hr):
    """a trace's design units (u 0 back .. 1 front, h up, in lengths) -> frame fractions (a along the picture's x)"""
    return (1.0 - u if front == "left" else u), h / hr


def extents(points, bas):
    """(n, 3) world points -> (rmin, rmax, umin, umax, dmin, dmax) along the camera's right, up and dir"""
    d, r, u = bas
    pr, pu, pd = points @ r, points @ u, points @ d
    return (float(pr.min()), float(pr.max()), float(pu.min()), float(pu.max()), float(pd.min()), float(pd.max()))


def to_ab(P, bas, ext):
    """world points -> frame fractions: the model's silhouette box (ext) is the trace outline's box"""
    d, r, u = bas
    rmin, rmax, umin, umax = ext[:4]
    return (P @ r - rmin) / max(rmax - rmin, 1e-9), (P @ u - umin) / max(umax - umin, 1e-9)


def visibility_res(tex):
    """the long side, in pixels, of the depth picture that decides which texels a view sees: twice the map, 1024 to
    8192. (Capped at 4096 until 2026-11-18, card a2ym: a 4096 map was checked at 1x and 5,644 texels along the edges
    of faces the camera cannot see took the picture's colour - a median 152/255 off their own face, a fringe the
    game's 1024 copy shows; at 2x they match (median 4). The 8192 picture costs 0.75 GB and 5 s on a square view.)"""
    return int(min(8192, max(1024, 2 * tex)))


def view_geometry(ext, depth_range, res_long):
    """the orthographic camera of a view: square pixels, the silhouette box + 2% margin, placed beyond everything.
    -> {r0, u0 (the corner of pixel (0, 0), bottom-left), px (pixel size), w, h, d_cam, d_min}"""
    rmin, rmax, umin, umax = ext[:4]
    sr, su = max(rmax - rmin, 1e-4), max(umax - umin, 1e-4)
    pad = 0.02 * max(sr, su)
    px = (max(sr, su) + 2 * pad) / res_long
    w, h = int(math.ceil((sr + 2 * pad) / px - 1e-6)), int(math.ceil((su + 2 * pad) / px - 1e-6))
    dmin, dmax = depth_range
    return {"r0": (rmin + rmax) / 2 - w * px / 2, "u0": (umin + umax) / 2 - h * px / 2, "px": px, "w": w, "h": h,
            "d_cam": dmax + 1.0 + pad, "d_min": dmin}


def visible(P, N, bas, depth, hit, geom, tol):
    """texels first seen along the view: P (n, 3) world positions, N (n, 3) unit normals; depth (h, w) = dir . the
    surface point each pixel of the view sees (bottom row first), hit = a surface there. The tolerance grows on
    slanted faces (the pixel's sample lies up to a pixel away: slope-scaled, like a shadow map's bias)."""
    d, r, u = bas
    j = np.clip(((P @ r - geom["r0"]) / geom["px"]).astype(np.int64), 0, geom["w"] - 1)
    i = np.clip(((P @ u - geom["u0"]) / geom["px"]).astype(np.int64), 0, geom["h"] - 1)
    c = np.abs(N @ d)
    tan = np.sqrt(np.clip(1 - c * c, 0, 1)) / np.maximum(c, 0.2)
    eps = geom["px"] * (1.0 + 2.0 * tan) + tol
    return ~hit[i, j] | (P @ d >= depth[i, j] - eps)


def ramp(c, lo, hi):
    """smoothstep: 0 at or below lo (grazing), 1 from hi (facing the camera)"""
    t = np.clip((np.asarray(c, np.float64) - lo) / max(hi - lo, 1e-6), 0, 1)
    return t * t * (3 - 2 * t)


# ---------------------------------------------------------------------------------------------- pictures (pure)
def srgb_to_linear(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def bilinear(img, X, Y):
    """img (h, w[, c]) top row first; X, Y continuous picture coordinates (pixel k spans k..k+1, its centre k+0.5),
    clamped at the edges -> (n[, c])"""
    img = np.asarray(img)
    h, w = img.shape[:2]
    fx = np.clip(np.asarray(X, np.float64).ravel() - 0.5, 0, w - 1)
    fy = np.clip(np.asarray(Y, np.float64).ravel() - 0.5, 0, h - 1)
    x0, y0 = np.floor(fx).astype(np.int64), np.floor(fy).astype(np.int64)
    x1, y1 = np.minimum(x0 + 1, w - 1), np.minimum(y0 + 1, h - 1)
    tx, ty = fx - x0, fy - y0
    if img.ndim == 3:
        tx, ty = tx[:, None], ty[:, None]
    return (img[y0, x0] * (1 - tx) * (1 - ty) + img[y0, x1] * tx * (1 - ty) + img[y1, x0] * (1 - tx) * ty
            + img[y1, x1] * tx * ty)


def fill_rings(rings, w, h, ox=0.0, oy=0.0):
    """even-odd fill of polygons (picture coordinates) on a w x h grid whose pixel (i, j) centre is
    (ox + j + 0.5, oy + i + 0.5) -> bool (h, w). An outline with its holes cut out."""
    edges = []
    for ring in rings:
        pts = [(float(p[0]) - ox, float(p[1]) - oy) for p in ring]
        edges += [(pts[k - 1], pts[k]) for k in range(len(pts))]
    mask = np.zeros((h, w), bool)
    if not edges:
        return mask
    e = np.asarray(edges, np.float64)
    ex0, ey0, ex1, ey1 = e[:, 0, 0], e[:, 0, 1], e[:, 1, 0], e[:, 1, 1]
    xs = np.arange(w) + 0.5
    for row in range(h):
        yc = row + 0.5
        cross = (ey0 <= yc) != (ey1 <= yc)
        if not cross.any():
            continue
        xc = np.sort(ex0[cross] + (yc - ey0[cross]) * (ex1[cross] - ex0[cross]) / (ey1[cross] - ey0[cross]))
        mask[row] = (np.searchsorted(xc, xs) % 2) == 1
    return mask


def outline_pull(a, b, rings, hr, max_move=0.06, res=2048):
    """points in frame fractions (a across, b up: the outline's box is 0..1 x 0..1) -> their moves (da, db) that put
    every point OUTSIDE the outline — or inside one of its holes (a trigger guard's opening) — onto the nearest edge;
    points inside stay. rings: [(k, 2) arrays in frame fractions], the outline first, then its holes. Distances in
    the box's own proportions (b scaled by hr). A move longer than max_move (in box widths) is left alone: that is a
    framing error, not a bulge."""
    a, b = np.asarray(a, np.float64), np.asarray(b, np.float64)
    W, H = res, max(8, int(round(res * hr)))
    pix = [np.stack([np.asarray(rg)[:, 0] * W, (1 - np.asarray(rg)[:, 1]) * H], 1) for rg in rings if len(rg) >= 3]
    mask = fill_rings(pix, W, H)
    xi = np.clip((a * W).astype(np.int64), 0, W - 1)
    yi = np.clip(((1 - b) * H).astype(np.int64), 0, H - 1)
    out = ~mask[yi, xi]
    da, db = np.zeros(len(a)), np.zeros(len(a))
    if not out.any():
        return da, db
    seg0, seg1 = [], []
    for rg in rings:
        q = np.asarray(rg, np.float64) * np.array([1.0, hr])
        if len(q) >= 2:
            seg0.append(q)
            seg1.append(np.roll(q, -1, axis=0))
    s0, s1 = np.concatenate(seg0), np.concatenate(seg1)
    d = s1 - s0
    dd = np.maximum((d * d).sum(1), 1e-18)
    idx = np.nonzero(out)[0]
    P = np.stack([a[idx], b[idx] * hr], 1)
    best = np.zeros((len(idx), 2))
    for k in range(0, len(idx), 1024):   # (every point against every edge, in chunks)
        p = P[k:k + 1024]
        t = np.clip((((p[:, None, :] - s0[None]) * d[None]).sum(2)) / dd[None], 0, 1)
        q = s0[None] + t[..., None] * d[None]
        dist = ((q - p[:, None, :]) ** 2).sum(2)
        best[k:k + 1024] = q[np.arange(len(p)), dist.argmin(1)]
    move = best - P
    keep = np.hypot(move[:, 0], move[:, 1]) <= max_move
    da[idx[keep]] = move[keep, 0]
    db[idx[keep]] = move[keep, 1] / hr
    return da, db


def _shifted(m, dy, dx, fill=False):
    """m moved by (dy, dx) pixels (what was at (i, j) is at (i + dy, j + dx)), the edge filled"""
    out = np.full(m.shape, fill, dtype=m.dtype)
    h, w = m.shape[:2]
    if abs(dy) >= h or abs(dx) >= w:
        return out
    dst = (slice(max(dy, 0), h + min(dy, 0)), slice(max(dx, 0), w + min(dx, 0)))
    out[dst] = m[max(-dy, 0):h - max(dy, 0), max(-dx, 0):w - max(dx, 0)]
    return out


def inside_distance(mask, cap):
    """pixels from the nearest pixel outside the mask (8-neighbour steps: 1 on the edge), up to cap"""
    d = np.zeros(mask.shape, np.float32)
    cur = mask.astype(bool).copy()
    for _ in range(max(1, int(math.ceil(cap)))):
        d += cur
        nxt = cur.copy()
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy or dx:
                    nxt &= _shifted(cur, dy, dx)
        cur = nxt
        if not cur.any():
            break
    return d


def fill_outside(img, mask, steps=3):
    """the colours just outside the mask become their inside neighbours' (steps rings): bilinear sampling at the
    outline then never mixes the backdrop in"""
    out = img.astype(np.float32).copy()
    known = mask.astype(bool).copy()
    for _ in range(steps):
        acc = np.zeros(out.shape, np.float32)
        cnt = np.zeros(mask.shape, np.float32)
        kf = known.astype(np.float32)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy or dx:
                    acc += _shifted(out * kf[..., None], dy, dx, 0.0)
                    cnt += _shifted(kf, dy, dx, 0.0)
        new = ~known & (cnt > 0)
        if not new.any():
            break
        out[new] = acc[new] / cnt[new][:, None]
        known |= new
    return out


def box_blur(a, r):
    """two box passes of radius r (~ a gaussian), edge-padded; a: 2D"""
    r = max(1, int(r))
    k = 2 * r + 1
    out = np.asarray(a, np.float64)
    for _ in range(2):
        c = np.cumsum(np.pad(out, ((0, 0), (r + 1, r)), mode="edge"), axis=1)
        out = (c[:, k:] - c[:, :-k]) / k
        c = np.cumsum(np.pad(out, ((r + 1, r), (0, 0)), mode="edge"), axis=0)
        out = (c[k:, :] - c[:-k, :]) / k
    return out


def flatten_light(rgb, mask, strength, radius):
    """CRUDE de-lighting: each pixel divided by the large-scale brightness around it (a masked blur of the luminance,
    radius px), renormalised to the object's median brightness. Takes out broad light gradients and big soft shadows;
    keeps small shading (engraving depth, crevices) and cannot tell a dark paint from a shadow. 0 = as is, 1 = flat."""
    if strength <= 0 or not mask.any():
        return rgb
    lin = srgb_to_linear(rgb[..., :3])
    lum = lin @ np.array([0.2126, 0.7152, 0.0722])
    m = mask.astype(np.float64)
    lb = box_blur(lum * m, radius) / np.maximum(box_blur(m, radius), 1e-4)
    target = float(np.median(lum[mask]))
    flat = np.clip(lin * (target / np.maximum(lb, 0.02))[..., None], 0, 1)
    out = rgb.copy()
    out[..., :3] = rgb[..., :3] * (1 - strength) + linear_to_srgb(flat) * strength
    return out


# ---------------------------------------------------------------------------------------------- detail mode (pure)
DETAIL_GAIN = 0.5  # detail=1: the picture's strongest fine features change the material's colour by up to +-50%
DETAIL_FLOOR = 0.12  # a picture whose fine features are under ~12% darker / lighter is not amplified beyond its own


def masked_blur(a, mask, r):
    """the mean of `a` over the mask's pixels around each pixel (box radius r): a backdrop never leaks in"""
    if r < 1:
        return np.asarray(a, np.float64)
    m = mask.astype(np.float64)
    return box_blur(a * m, r) / np.maximum(box_blur(m, r), 1e-6)


def _slide(a, r, fn):
    """a square r-neighbourhood max (fn=np.maximum) or min (np.minimum), separable, edge-replicated"""
    out = a
    for axis in (0, 1):
        pad = [(0, 0), (0, 0)]
        pad[axis] = (r, r)
        p = np.pad(out, pad, mode="edge")
        n, acc = out.shape[axis], None
        for k in range(2 * r + 1):
            v = p[k:k + n] if axis == 0 else p[:, k:k + n]
            acc = v if acc is None else fn(acc, v)
        out = acc
    return out


def fine_structure(a, mask, r_lo, r_se):
    """THIN features of a (log luminance) inside the mask, in a's own units: bright ones (a - its opening) minus dark
    ones (its closing - a), with a square element of radius r_se (morphological top-hats: a line narrower than
    2 r_se + 1 px is kept; a light gradient, the inside of a big shadow and a shadow's EDGE — a step, not a line —
    give ~0). r_lo first blurs away what is finer than half a texel (noise, aliasing). Outside the mask, the nearest
    inside values (a backdrop never reads as an edge)."""
    r = max(1, int(round(r_se)))
    a = fill_outside(np.asarray(a, np.float64)[..., None], mask, steps=r + 2)[..., 0]
    if r_lo >= 1:
        a = box_blur(a, r_lo)
    closing = _slide(_slide(a, r, np.maximum), r, np.minimum)
    opening = _slide(_slide(a, r, np.minimum), r, np.maximum)
    return ((a - opening) - (closing - a)) * mask


def detail_radii(px_per_texel, detail_px=None):
    """picture-pixel radii of the detail extraction: below half a texel is finer than the map can hold (r_lo); a
    feature up to ~2 x `detail_px` wide is detail, wider is form or light (default 5 texels, at least 3 px, at most
    32: the element's cost) -> (r_lo, r_hi)"""
    r_lo = 0.5 * px_per_texel if px_per_texel >= 2 else 0.0
    r_hi = float(detail_px) if detail_px else max(3.0, 5.0 * px_per_texel)
    return r_lo, min(max(r_hi, r_lo + 2.0), 32.0)


def log_luminance(rgb):
    lum = srgb_to_linear(rgb[..., :3]) @ np.array([0.2126, 0.7152, 0.0722])
    return np.log(np.maximum(lum, 1e-3))


def detail_signal(rgb, mask, r_lo, r_hi, floor=DETAIL_FLOOR):
    """a picture's FINE structure with its light taken out: the thin features (fine_structure) of its LOG luminance (a
    line in the shade and the same line in the light give the same value; a light gradient, a big shadow and its edge
    give ~0), faded in over r_hi / 2 from the mask's edge (a photo's rim light / edge darkening is not engraving),
    normalised PER PICTURE — divided by its 98th percentile (at least `floor`: a picture with no fine structure is
    not amplified into noise) and soft-limited (tanh) — then re-centred (minus its local mean over 2 r_hi) so every
    region keeps its mean colour. -> (signal (h, w) in about -1..1, the scale it was divided by: log units)"""
    hp = fine_structure(log_luminance(rgb), mask, r_lo, r_hi)
    fade = np.clip(inside_distance(mask, max(1.0, r_hi / 2)) / max(1.0, r_hi / 2), 0, 1)
    hp = hp * fade
    vals = np.abs(hp[mask & (fade >= 1)])
    scale = max(float(np.percentile(vals, 98)) if vals.size else 0.0, floor)
    t = np.tanh(hp / scale)
    t = (t - masked_blur(t, mask, 2 * r_hi)) * mask  # (a dark line alone would darken its region on average)
    return t.astype(np.float32), scale


def relief_signal(path, size, window, mask, length_px):
    """a `kit vision relief` height field (its own pixels: the cut-out the trace was made on, maybe smaller) -> the
    picture window's SHAPE signal: the height minus its broad form (a blur over 3 % of the outline's length — the mesh
    has the form; the panels, serrations, levers and stippling are what is left), normalised like detail_signal
    (98th percentile, soft-limited, -1..1). Raised = positive."""
    z = np.load(path if os.path.isabs(path) else os.path.join(os.getcwd(), path))
    h = z["height"].astype(np.float32)
    W, H = size
    if h.shape != (H, W):  # (computed on a smaller copy: scaled up to the picture's pixels — numpy: Blender has no PIL)
        sy, sx = h.shape
        ys = np.clip((np.arange(H) + 0.5) * (sy / H) - 0.5, 0, sy - 1)
        xs = np.clip((np.arange(W) + 0.5) * (sx / W) - 0.5, 0, sx - 1)
        y0, x0 = np.floor(ys).astype(np.int64), np.floor(xs).astype(np.int64)
        y1, x1 = np.minimum(y0 + 1, sy - 1), np.minimum(x0 + 1, sx - 1)
        fy, fx = (ys - y0)[:, None], (xs - x0)[None, :]
        h = ((h[y0][:, x0] * (1 - fx) + h[y0][:, x1] * fx) * (1 - fy)
             + (h[y1][:, x0] * (1 - fx) + h[y1][:, x1] * fx) * fy).astype(np.float32)
    cy0, cy1, cx0, cx1 = window
    h = h[cy0:cy1, cx0:cx1].astype(np.float64)
    r = max(2, int(round(0.03 * length_px)))
    hp = (h - masked_blur(h, mask, r)) * mask
    vals = np.abs(hp[mask])
    scale = max(float(np.percentile(vals, 98)) if vals.size else 0.0, 1e-6)
    return (np.tanh(hp / scale) * mask).astype(np.float32)


def modulate(base_srgb, d):
    """the material's colour (sRGB 0..1, (n, 3)) times (1 + d) in LINEAR light (the picture's luminance ratio applied
    to the albedo), clamped -> sRGB"""
    m = np.clip(1.0 + np.asarray(d, np.float64), 0.1, 1.9)
    return linear_to_srgb(srgb_to_linear(base_srgb) * m[:, None])


def texel_slope(h, ok, pos):
    """UV-space slope of a texel height field (H, W; rows run +V) — only between neighbouring texels of ONE surface
    (both hold a surface and their world points are within 3x the median texel spacing: never across a UV seam);
    one-sided at an island's edge -> (gx, gy) per texel"""
    out = []
    near = []
    for axis in (1, 0):
        nb = np.roll(pos, -1, axis)
        both = ok & np.roll(ok, -1, axis)
        if axis == 1:
            both[:, -1] = False
        else:
            both[-1, :] = False
        near.append(np.linalg.norm(nb - pos, axis=-1)[both])
    near = np.concatenate(near)
    tol = 3.0 * float(np.median(near)) if near.size else 0.0
    for axis in (1, 0):
        fwd, bwd = np.roll(h, -1, axis), np.roll(h, 1, axis)
        okf = ok & np.roll(ok, -1, axis) & (np.linalg.norm(np.roll(pos, -1, axis) - pos, axis=-1) <= tol)
        okb = ok & np.roll(ok, 1, axis) & (np.linalg.norm(np.roll(pos, 1, axis) - pos, axis=-1) <= tol)
        if axis == 1:
            okf[:, -1], okb[:, 0] = False, False
        else:
            okf[-1, :], okb[0, :] = False, False
        g = np.where(okf & okb, (fwd - bwd) / 2, np.where(okf, fwd - h, np.where(okb, h - bwd, 0.0)))
        out.append(g)
    return out[0], out[1]


def apply_bump(nrm, gx, gy, strength):
    """tilt a tangent-space normal map (H, W, 3+, values 0..1) by a height field's slope (the kit's pattern relief
    does the same): the surface leans away from where the height rises -> the new map"""
    nv = nrm[..., :3] * 2 - 1
    nv[..., 0] -= gx * strength
    nv[..., 1] -= gy * strength
    nv /= np.linalg.norm(nv, axis=-1, keepdims=True) + 1e-9
    out = nrm.copy()
    out[..., :3] = nv * 0.5 + 0.5
    return out


def pearson(a, b):
    a, b = np.asarray(a, np.float64).ravel(), np.asarray(b, np.float64).ravel()
    a, b = a - a.mean(), b - b.mean()
    den = math.sqrt(float((a * a).sum() * (b * b).sum()))
    return float((a * b).sum() / den) if den > 0 else 0.0


def object_mask(rgba, bg="auto", threshold=28.0, region=None):
    """what is the object in a picture (kit trace's own rule, values 0..1): the alpha channel when it has real
    transparency, else the colour distance (0..255 units) from the backdrop (the WHOLE picture's border median, or
    black / white) — judged on the whole picture, measured only in region (y0, y1, x0, x1) when given"""
    y0, y1, x0, x1 = region or (0, rgba.shape[0], 0, rgba.shape[1])
    a = rgba[..., 3]
    if (a < 16 / 255).mean() > 0.05:
        return a[y0:y1, x0:x1] > 0.5
    if bg == "dark":
        ref = np.zeros(3)
    elif bg == "light":
        ref = np.full(3, 255.0)
    else:
        ref = np.median(np.concatenate([rgba[0, :, :3], rgba[-1, :, :3], rgba[:, 0, :3], rgba[:, -1, :3]]), 0) * 255
    px = rgba[y0:y1, x0:x1, :3].astype(np.float64) * 255.0
    return np.sqrt(((px - ref) ** 2).sum(-1)) > threshold


def best_shift(outline, obj, search):
    """where the picture's object sits against the traced outline: the integer (dx, dy) that, moving the outline by
    it, best overlaps the object (IoU) — a pyramid: every shift on a coarse grid, then +-2 steps per finer level.
    -> (dx, dy, iou at that shift, iou unmoved)"""
    def iou(a, b):
        u = (a | b).sum()
        return float((a & b).sum() / u) if u else 0.0

    levels = {}

    def at(f, dx, dy):  # the IoU with the outline moved (dx, dy) px, both masks sampled every f px
        if f not in levels:
            levels[f] = (outline[::f, ::f], obj[::f, ::f])
        so, sb = levels[f]
        return iou(_shifted(so, dy // f, dx // f), sb)

    f = 1
    while search / f > 24:
        f *= 2
    s = int(math.ceil(search / f))
    best, val = (0, 0), at(f, 0, 0)
    for dy in range(-s, s + 1):
        for dx in range(-s, s + 1):
            v = at(f, dx * f, dy * f)
            if v > val + 1e-9:
                best, val = (dx * f, dy * f), v
    while f > 1:
        f //= 2
        bx, by = best
        val = at(f, bx, by)
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                v = at(f, bx + dx * f, by + dy * f)
                if v > val + 1e-9:
                    best, val = (bx + dx * f, by + dy * f), v
    return best[0], best[1], at(1, *best), iou(outline, obj)


def alignment(outline, obj, search, erode=2):
    """is the picture where its trace says? -> facts: the share of the outline's core (eroded `erode` px: an outline's
    own edge is never exact) where the picture shows its BACKDROP, and the shift that would line them up"""
    core = inside_distance(outline, erode + 1) > erode
    if not core.any():
        core = outline
    off = float((core & ~obj).sum() / max(1, core.sum()))
    dx, dy, best, now = best_shift(outline, obj, search)
    return {"outline_on_backdrop_pct": round(100 * off, 1), "shift_px": [int(dx), int(dy)],
            "iou": round(now, 3), "iou_if_shifted": round(best, 3)}


def misplaced(align, length_px):
    """is the picture's object somewhere else than its trace says? Judged by the SHIFT that lines them up (at least
    3 px and 1% of the length, and it must improve the overlap by 2 points) — never by the backdrop share alone: a
    highlight as white as the backdrop lies inside the object and moves nothing"""
    if "shift_px" not in align:
        return False
    dx, dy = align["shift_px"]
    return max(abs(dx), abs(dy)) >= max(3.0, 0.01 * length_px) and align["iou_if_shifted"] - align["iou"] >= 0.02


def homography(src, dst):
    """3 x 3 H with dst ~ H @ (x, y, 1) for 4 point pairs (DLT)"""
    rows = []
    for (x, y), (u, v) in zip(src, dst):
        rows.append([x, y, 1, 0, 0, 0, -u * x, -u * y, -u])
        rows.append([0, 0, 0, x, y, 1, -v * x, -v * y, -v])
    _, _, vt = np.linalg.svd(np.asarray(rows, np.float64))
    hm = vt[-1].reshape(3, 3)
    return hm / hm[2, 2]


def corners_of(box):
    """a box (x0, y0, x1, y1) or 4 corners ((x, y) top-left, top-right, bottom-right, bottom-left) -> (4, 2)"""
    b = np.asarray(box, np.float64)
    if b.shape == (4,):
        x0, x1 = sorted((b[0], b[2]))
        y0, y1 = sorted((b[1], b[3]))
        return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]])
    if b.shape != (4, 2):
        raise ValueError("box: 4 numbers (x0, y0, x1, y1) or 4 corners ((x, y) top-left, top-right, bottom-right, "
                         "bottom-left) in the picture's pixels")
    return b


def straighten(img, box, size=None):
    """cut a marking out of a picture as an upright patch: a box is cropped, a quad (4 corners, TL TR BR BL) is
    straightened (perspective: a homography) -> (h, w, channels), top row first"""
    c = corners_of(box)
    if size is None:
        w = (np.linalg.norm(c[1] - c[0]) + np.linalg.norm(c[2] - c[3])) / 2
        h = (np.linalg.norm(c[3] - c[0]) + np.linalg.norm(c[2] - c[1])) / 2
        size = (max(2, int(round(w))), max(2, int(round(h))))
    w, h = size
    hm = homography([(0, 0), (w, 0), (w, h), (0, h)], c)  # patch -> picture
    jj, ii = np.meshgrid(np.arange(w) + 0.5, np.arange(h) + 0.5)
    p = hm @ np.stack([jj.ravel(), ii.ravel(), np.ones(w * h)])
    return bilinear(img, p[0] / p[2], p[1] / p[2]).reshape(h, w, -1)


# ---------------------------------------------------------------------------------------------- compositing (pure)
def match_to_pictures(base, out, alpha, midx, mats, real, imported):
    """a GENERATED material's own colour (its painter's guess) matched to the pictures where they cover it well:
    per such material, each channel's mean and spread over the well-covered texels moved to the pictures' (the
    spread ratio kept within 0.5-2) and applied to all its texels -> new base (n, 3), or None when nothing qualifies.
    Unmatched, the Glock's painted grey showed as pale patches wherever the black photos stopped. A designed (kit)
    material is never changed."""
    base = np.asarray(base, np.float64)
    if not imported:
        return None
    new, changed = base.copy(), False
    well = (alpha > 0.9) & real
    for k in np.unique(midx):
        if not (0 <= k < len(mats)) or mats[k] is None or mats[k].name not in imported:
            continue
        sel = midx == k
        c = sel & well
        if c.sum() < max(500, 0.05 * sel.sum()):
            continue
        mb, sb = base[c].mean(0), base[c].std(0) + 1e-6
        mo, so = out[c].mean(0), out[c].std(0) + 1e-6
        new[sel] = np.clip((base[sel] - mb) * np.clip(so / sb, 0.5, 2.0) + mo, 0, 1)
        changed = True
    return new if changed else None


def blend(base, layers, decals=()):
    """base (n, 3) colours; layers: [(rgb (n, 3), w (n,), c (n,))] pictures (w = how much: mix x facing ramp x
    outline x visible, c = |n.v|), blended by w * c^6 with their union coverage 1 - prod(1 - w); decals: [(rgb, w)]
    painted over that in order. -> (colours (n, 3), alpha (n,): how much of each texel is picture)"""
    out = np.asarray(base, np.float64).copy()
    alpha = np.zeros(len(out))
    if layers:
        num = np.zeros_like(out)
        den = np.zeros(len(out))
        miss = np.ones(len(out))
        for rgb, w, c in layers:
            bw = w * np.asarray(c, np.float64) ** BLEND_POWER
            num += rgb * bw[:, None]
            den += bw
            miss *= 1 - w
        alpha = 1 - miss
        ok = den > 1e-12
        col = np.where(ok[:, None], num / np.maximum(den, 1e-12)[:, None], out)
        out = out * (1 - alpha[:, None]) + col * alpha[:, None]
    for rgb, w in decals:
        out = out * (1 - w[:, None]) + rgb * w[:, None]
        alpha = 1 - (1 - alpha) * (1 - w)
    return out, alpha


def cells_compare(a, b, model, picture, cols, rows, min_px=25):
    """the model seen from a view against its picture, cell by cell (a, b in 0..1 over the outline's box; colours
    sRGB 0..1): mean colours (a texture's blur keeps a mean, not a median) -> [{a, b, delta_e, px}]"""
    from rbx_colour import srgb_to_lab  # noqa: PLC0415

    out = []
    ca = np.clip((a * cols).astype(np.int64), 0, cols - 1)
    cb = np.clip((b * rows).astype(np.int64), 0, rows - 1)
    for i in range(rows):
        for j in range(cols):
            sel = (ca == j) & (cb == i)
            n = int(sel.sum())
            if n < min_px:
                continue
            m, p = model[sel].mean(0), picture[sel].mean(0)
            de = float(np.linalg.norm(srgb_to_lab(m) - srgb_to_lab(p)))
            out.append({"a": [round(j / cols, 3), round((j + 1) / cols, 3)],
                        "b": [round(i / rows, 3), round((i + 1) / rows, 3)], "delta_e": round(de, 1), "px": n})
    return out


# ---------------------------------------------------------------------------------------------- layers
def trace_path(trace, repo):
    """a trace name (assets/models/<name>.trace.json) or a path to a .trace.json -> absolute path"""
    p = trace if trace.endswith(".trace.json") else os.path.join("assets", "models", f"{trace}.trace.json")
    return p if os.path.isabs(p) else os.path.join(repo, p)


def load_trace(trace, repo):
    path = trace_path(trace, repo)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"no trace {path} — lune run kit trace <picture> --name <name> first")
    with open(path, encoding="utf-8") as fh:
        return path, json.load(fh)


def _sha(path):
    h = hashlib.sha1()
    with open(path, "rb") as fh:
        h.update(fh.read())
    return h.hexdigest()[:16]


def make_layer(kind, name, trace, repo, view, **opt):
    """a.project / a.decal -> a layer (checked now: a wrong trace, view or picture fails at the call, not the bake)"""
    if view not in VIEWS:
        raise ValueError(f'{kind}: view="{view}" — use one of {", ".join(VIEWS)}')
    tpath, t = load_trace(trace, repo)
    frame(t)  # (raises: a trace without a picture frame cannot be projected)
    src = (t.get("source") or "").replace("\\", "/")
    pic = opt.get("picture") or src
    pic_abs = pic if os.path.isabs(pic) else os.path.join(repo, pic)
    if not os.path.isfile(pic_abs):
        raise FileNotFoundError(f"{kind}: the picture {pic} is not there (the trace {os.path.basename(tpath)} was "
                                "made on it) — put it back, or re-trace")
    mix = float(opt.get("mix", 1.0))
    if not 0.0 <= mix <= 1.0:
        raise ValueError(f"{kind}: mix={mix} — 0 (the material) .. 1 (the picture)")
    lo, hi = (float(v) for v in opt.get("facing", (0.25, 0.6)))
    if not 0.0 <= lo < hi <= 1.0:
        raise ValueError(f"{kind}: facing=({lo}, {hi}) — 0 <= grazing < full <= 1 (|n.v|)")
    if opt.get("mirror") and view != "side":
        raise ValueError(f"{kind}: mirror=True paints the OTHER side of a side view — not for a {view} view")
    layer = {"kind": kind, "name": name, "view": view, "front": t.get("front", "right"),
             "trace": os.path.relpath(tpath, repo).replace("\\", "/"), "picture": pic.replace("\\", "/"),
             "mix": mix, "facing": (lo, hi), "feather": float(opt.get("feather", 3.0)),
             "flatten": float(opt.get("flatten", 0.0)), "mirror": bool(opt.get("mirror", False)),
             "parts": tuple(opt["parts"]) if opt.get("parts") else None,
             "materials": tuple(opt["materials"]) if opt.get("materials") else None,
             "ignore": tuple(opt["ignore"]) if opt.get("ignore") is not None else None}
    if kind == "decal":
        layer["box"] = corners_of(opt["box"]).tolist()
        layer["at"] = tuple(float(v) for v in opt["at"]) if opt.get("at") is not None else None
        layer["size"] = tuple(float(v) for v in opt["size"]) if opt.get("size") is not None else None
        if opt.get("picture") and (layer["at"] is None or layer["size"] is None):
            raise ValueError(f"decal {name}: cut from another picture than the trace's — say where it goes: "
                             "at=(u, h) and size=(w, h) in the trace's design units (u 0 back .. 1 front, "
                             "h up, in lengths)")
    if not 0.0 <= layer["flatten"] <= 1.0:
        raise ValueError(f"{kind}: flatten={layer['flatten']} — 0 (as photographed) .. 1 (crudely flat)")
    if kind == "project":
        layer["detail"] = float(opt.get("detail") or 0.0)
        layer["detail_px"] = float(opt["detail_px"]) if opt.get("detail_px") else None
        layer["bump"] = float(opt.get("bump") or 0.0)
        if not 0.0 <= layer["detail"] <= 2.0:
            raise ValueError(f"project: detail={layer['detail']} — 0 (paint the picture's colour) .. 1 (its fine "
                             "structure at full strength; up to 2 exaggerates)")
        if layer["detail_px"] is not None and layer["detail_px"] < 1:
            raise ValueError(f"project: detail_px={layer['detail_px']} — picture pixels, at least 1")
        if layer["bump"] and not layer["detail"]:
            raise ValueError("project: bump= is the detail's relief in the normal map — it needs detail= > 0")
        if not 0.0 <= layer["bump"] <= 4.0:
            raise ValueError(f"project: bump={layer['bump']} — 0 (none) .. 1 (engraving depth) .. 4")
        # relief= (COLOUR mode): the picture's colour is painted AND its fine structure goes into the normal map —
        # a photo of the object itself (its colour is right) whose serrations, stippling and engraving should also
        # catch the light; in detail mode that is bump=
        layer["relief"] = float(opt.get("relief") or 0.0)
        layer["relief_map"] = None
        if opt.get("relief_map"):  # (a picture's sculpted relief, `kit vision relief`: its shape, not only its lines)
            rm = opt["relief_map"]
            rm_abs = rm if os.path.isabs(rm) else os.path.join(repo, rm)
            if not os.path.isfile(rm_abs):
                raise FileNotFoundError(f"project: relief_map {rm} not found — lune run kit vision relief <cut-out>")
            if not layer["relief"]:
                raise ValueError("project: relief_map= needs relief= > 0 (its strength in the normal map)")
            layer["relief_map"] = rm_abs.replace("\\", "/")
        if layer["relief"] and layer["detail"]:
            raise ValueError("project: relief= is the colour mode's relief — in detail mode (detail= > 0) use bump=")
        if not 0.0 <= layer["relief"] <= 4.0:
            raise ValueError(f"project: relief={layer['relief']} — 0 (none) .. 1 (engraving depth) .. 4")
    digest = hashlib.sha1(json.dumps({k: v for k, v in layer.items()}, sort_keys=True, default=str).encode())
    digest.update(_sha(tpath).encode())
    digest.update(_sha(pic_abs).encode())
    if layer.get("relief_map"):
        digest.update(_sha(layer["relief_map"]).encode())
    layer["digest"] = digest.hexdigest()[:16]
    return layer


def prepare_picture(rgba, trace, layer, px_per_texel=None):
    """the picture as the bake samples it, around the trace's box: the backdrop outside the outline replaced by the
    nearest trusted colour (the edge band, feather px, too), optionally de-lit; the outline as a weight (one pixel
    wider: the silhouette's edge lands on it); the picture's own object mask (when its backdrop says it) and whether it
    lines up with the trace; in detail mode its fine-structure signal (detail_signal, radii from the picture pixels
    per texel of the model's map). rgba: (H, W, 4) top row first, sRGB 0..1."""
    fr = frame(trace)
    x0, y1, L, hr = fr
    H, W = rgba.shape[:2]
    feather = max(0.0, layer["feather"])
    m = int(math.ceil(max(8.0, 2 * feather + 4, 0.05 * L)))
    cx0, cy0 = max(0, int(math.floor(x0)) - m), max(0, int(math.floor(y1 - hr * L)) - m)
    cx1, cy1 = min(W, int(math.ceil(x0 + L)) + m), min(H, int(math.ceil(y1)) + m)
    if cx1 - cx0 < 2 or cy1 - cy0 < 2:
        raise ValueError(f"the trace's frame ({x0:.0f}, {y1:.0f}, {L:.0f} px) lies outside its picture ({W} x {H})")
    crop = rgba[cy0:cy1, cx0:cx1].astype(np.float32)
    front = trace.get("front", "right")

    def ring(pts):
        u, hh = np.asarray(pts, np.float64).T
        a = 1 - u if front == "left" else u
        return np.stack([x0 + a * L, y1 - hh * L], 1)

    rings = [ring(trace["outline"])] + [ring(hh) for hh in trace.get("holes", []) if len(hh) >= 3]
    outline = fill_rings(rings, cx1 - cx0, cy1 - cy0, cx0, cy0)
    dist = inside_distance(outline, max(feather, 1.0) + 2)
    # the outline's edge band (feather px: a photo's edge pixels are half backdrop) and everything outside it take the
    # colour from just inside; the weight stays whole up to a pixel past the outline (the model's silhouette edge lands
    # ON the outline: a fade there left a rim of the material's colour round every face)
    trusted = (dist > feather) & (crop[..., 3] > 0.5)
    if not trusted.any():
        trusted = outline & (crop[..., 3] > 0.5)
    img = fill_outside(crop, trusted, steps=int(math.ceil(feather)) + 3)
    soft = outline.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            soft |= _shifted(outline, dy, dx)
    soft = soft.astype(np.float32)
    if layer["flatten"] > 0 and not layer.get("detail"):
        img = flatten_light(img, outline, layer["flatten"], max(4, int(L / 12)))
    detail = None
    if (layer.get("detail") or layer.get("relief")) and px_per_texel:
        # detail mode: the picture's fine structure only (its own colour, light and shadows never reach the map)
        r_lo, r_hi = detail_radii(px_per_texel, layer.get("detail_px"))
        sig, scale = detail_signal(crop, trusted, r_lo, r_hi)
        detail = {"signal": sig, "scale": scale, "r_lo": r_lo, "r_hi": r_hi, "px_per_texel": px_per_texel}
        if layer.get("relief_map"):
            detail["shape"] = relief_signal(layer["relief_map"], (W, H), (cy0, cy1, cx0, cx1), trusted, L)
    how = str(trace.get("mask") or "backdrop")
    measurable = how.startswith(("alpha", "backdrop"))
    obj, align = None, {"note": f"not measured: the trace's object came from {how!r}, not the picture's backdrop"}
    if measurable:
        obj = object_mask(rgba, trace.get("bg", "auto"), float(trace.get("threshold", 28.0)), (cy0, cy1, cx0, cx1))
        align = alignment(outline, obj, search=max(4, int(0.2 * L)))
    return {"fr": fr, "off": (cx0, cy0), "img": img, "soft": soft.astype(np.float32), "dist": dist,
            "outline": outline, "obj": obj, "align": align, "size": (W, H), "detail": detail}


def decal_patch(rgba, trace, layer):
    """the marking straightened out of its picture and where it goes: (patch (h, w, 4), (a0, a1, b0, b1)) in the
    trace's frame fractions — at its measured place (the box through the trace's frame), or at= / size= (design
    units: u 0 back .. 1 front, h up, in lengths)"""
    fr = frame(trace)
    c = np.asarray(layer["box"], np.float64)
    patch = straighten(rgba, c)
    if layer["at"] is None:
        a, b = from_picture(c[:, 0], c[:, 1], fr)
        a0, a1, b0, b1 = float(a.min()), float(a.max()), float(b.min()), float(b.max())
    else:
        hr = fr[3]
        ac, bc = design_to_ab(layer["at"][0], layer["at"][1], trace.get("front", "right"), hr)
        if layer["size"] is not None:
            da, db = layer["size"][0], layer["size"][1] / hr
        else:
            a, b = from_picture(c[:, 0], c[:, 1], fr)
            da, db = float(a.max() - a.min()), float(b.max() - b.min())
        a0, a1, b0, b1 = ac - da / 2, ac + da / 2, bc - db / 2, bc + db / 2
    return patch.astype(np.float32), (a0, a1, b0, b1)


def sample_decal(patch, rect, a, b, feather):
    """a decal's colour and weight at frame fractions (a, b): inside its rectangle, faded over `feather` patch pixels
    at its border, times its own alpha -> (rgb (n, 3), w (n,))"""
    a0, a1, b0, b1 = rect
    h, w = patch.shape[:2]
    X = (a - a0) / max(a1 - a0, 1e-9) * w
    Y = (b1 - b) / max(b1 - b0, 1e-9) * h
    inside = (X >= 0) & (X <= w) & (Y >= 0) & (Y <= h)
    edge = np.minimum(np.minimum(X, w - X), np.minimum(Y, h - Y))
    wt = np.where(inside, np.clip(edge / feather, 0, 1) if feather > 0 else 1.0, 0.0)
    s = bilinear(patch, X, Y)
    return s[:, :3], wt * np.clip(s[:, 3], 0, 1)


def passes(layer):
    """the cameras a layer paints from: [(basis key, flip a)] — mirror=True adds the other side, picture mirrored"""
    v, f = layer["view"], layer["front"] if layer["view"] in ("side", "top") else "right"
    out = [((v, f), False)]
    if layer.get("mirror"):
        out.append(((v, "left" if f == "right" else "right"), True))
    return out


# ---------------------------------------------------------------------------------------------- Blender side
def load_picture(path):
    """a picture -> (H, W, 4) sRGB values 0..1, top row first (a float picture is encoded to sRGB: the colour map's
    values are)"""
    import bpy  # noqa: PLC0415

    im = bpy.data.images.load(path, check_existing=False)
    try:
        w, h = im.size
        px = np.empty(w * h * 4, np.float32)
        im.pixels.foreach_get(px)
        px = px.reshape(h, w, 4)[::-1]  # (a view: a 12 MP photo is 190 MB as floats already)
        if im.is_float and im.colorspace_settings.name != "Non-Color":  # (16-bit PNG, EXR: held linear)
            px[..., :3] = linear_to_srgb(px[..., :3])
        return px
    finally:
        bpy.data.images.remove(im)


def save_picture(arr, path):
    """(H, W, 3|4) values 0..1, top row first -> an 8-bit PNG (the values kept as they are)"""
    import bpy  # noqa: PLC0415

    arr = np.asarray(arr, np.float32)
    if arr.shape[2] == 3:
        arr = np.concatenate([arr, np.ones(arr.shape[:2] + (1,), np.float32)], 2)
    h, w = arr.shape[:2]
    img = bpy.data.images.new(os.path.basename(path), w, h, alpha=True)
    img.pixels.foreach_set(np.ascontiguousarray(arr[::-1]).ravel())
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)


def _alive(o):
    try:
        return o is not None and o.name is not None
    except ReferenceError:
        return False


def _world_points(o):
    me = o.data
    co = np.empty(len(me.vertices) * 3, np.float64)
    me.vertices.foreach_get("co", co)
    mw = np.array(o.matrix_world, np.float64)
    return co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3]


def prepare_all(asset, repo, geo=False):
    """at build(), before the first join: every layer's picture (sampled, its outline, its alignment) and, for a full
    build, the model's silhouette box per camera (without the layer's ignore= groups; floaters are baked, not seen)
    -> {"layers": {i: prep}, "depth": (dmin, dmax) per camera key}"""
    pics, prep = {}, {}
    floaters = {id(o) for o, _g in asset._floater_parts}
    pts, areas, by_part = {}, {}, {}
    if not geo:
        for o, g in asset.parts:
            if o.type == "MESH" and id(o) not in floaters and len(o.data.vertices):
                wp = _world_points(o)
                pts.setdefault(g, []).append(wp)
                by_part.setdefault(o.name.split("~")[0], []).append(wp)
                scale = abs(np.linalg.det(np.array(o.matrix_world, np.float64)[:3, :3])) ** (2 / 3)
                areas[g] = areas.get(g, 0.0) + sum(f.area for f in o.data.polygons) * scale
        pts = {g: np.concatenate(v) for g, v in pts.items()}
    every = np.concatenate(list(pts.values())) if pts else None
    names = {v["mat"].name: k for k, v in asset.mats.items()}
    for i, layer in enumerate(asset.projections):
        _, t = load_trace(layer["trace"], repo)
        if layer["ignore"] is None:  # the trace_match of this view on this trace: the groups it does not show
            ref = asset.reference.get(layer["view"])
            same = bool(ref) and os.path.relpath(os.path.abspath(os.path.join(repo, ref)), repo).replace(
                "\\", "/") == layer["trace"]
            layer["ignore"] = tuple(asset.ref_options.get(layer["view"], {}).get("ignore", ())) if same else ()
        if layer["materials"]:
            bad = [m for m in layer["materials"] if m not in asset.mats]
            if bad:
                raise ValueError(f"{layer['kind']} {layer['name']}: no material {', '.join(bad)} — the materials are "
                                 f"{', '.join(asset.mats)}")
        key = layer["picture"]
        if key not in pics:
            pics[key] = load_picture(key if os.path.isabs(key) else os.path.join(repo, key))
        p = {"trace": t, "cams": {}}
        px_per_texel = None
        # the trace_match of this view on this trace laid the model on the picture by a PART (align=): so does the
        # projection — else a part that sticks out differently (a cocked hammer, a longer tang) moves every painted
        # marking with the whole outline's box
        ref_ = asset.reference.get(layer["view"])
        opts_ = asset.ref_options.get(layer["view"], {})
        on_ref = bool(ref_) and os.path.relpath(os.path.abspath(os.path.join(repo, ref_)), repo).replace(
            "\\", "/") == layer["trace"]
        align_ = opts_.get("align") if on_ref else None
        align_pts = None
        if align_ and pts:
            names_ = (opts_.get("parts") or {}).get(align_) or []
            got_ = [w for n_ in names_ for w in by_part.get(n_, [])]
            tring = (t.get("parts") or {}).get(align_)
            if not got_ or not tring:
                raise ValueError(f"{layer['kind']} {layer['name']}: align={align_!r} needs the part traced in the "
                                 f"picture and its model parts ({', '.join(names_) or 'none'}) built")
            align_pts = np.concatenate(got_)
            hr_ = max(float(t.get("height_ratio", 0.3)), 0.01)
            us_, hs_ = [q[0] for q in tring], [q[1] for q in tring]
            (aa, ba), (ab_, bb) = (design_to_ab(min(us_), min(hs_), t.get("front", "right"), hr_),
                                   design_to_ab(max(us_), max(hs_), t.get("front", "right"), hr_))
            a0_, a1_ = sorted((aa, ab_))
            b0_, b1_ = sorted((ba, bb))
        if pts:
            shown_g = [g for g in pts if g not in layer["ignore"]]
            if not shown_g:
                raise ValueError(f"{layer['kind']} {layer['name']}: every group is in ignore={layer['ignore']}")
            shown = np.concatenate([pts[g] for g in shown_g])
            for key_, _flip in passes(layer):
                bas = basis(*key_)
                ext = extents(shown, bas)
                if align_pts is not None:  # the box the aligned part puts the whole outline in
                    pe = extents(align_pts, bas)
                    w_ = (pe[1] - pe[0]) / max(a1_ - a0_, 1e-9)
                    rmin_ = pe[0] - a0_ * w_
                    h_ = hr_ * w_
                    umin_ = (pe[2] + pe[3]) / 2 - (b0_ + b1_) / 2 * h_
                    ext = (rmin_, rmin_ + w_, umin_, umin_ + h_, ext[4], ext[5])
                d_all = extents(every, bas)
                p["cams"][key_] = {"bas": bas, "ext": ext, "depth": (d_all[4], d_all[5])}
            # picture pixels per texel of the map (the biggest painted group's: texels per stud ~ tex / sqrt(area
            # x 1.4), the kit's own packing estimate) — what the detail band-pass is tied to
            ext = p["cams"][passes(layer)[0][0]]["ext"]
            g_big = max(shown_g, key=lambda g: areas.get(g, 0.0))
            tps = asset.group_tex.get(g_big, asset.tex) / math.sqrt(max(areas.get(g_big, 0.0), 1e-6) * 1.4)
            px_per_texel = frame(t)[2] / max(ext[1] - ext[0], 1e-6) / tps
        if layer["kind"] == "decal":
            p["patch"], p["rect"] = decal_patch(pics[key], t, layer)
            p["fr"] = frame(t)
        else:
            p.update(prepare_picture(pics[key], t, layer, px_per_texel))
        p["mats"] = {asset.mats[m]["mat"].name for m in layer["materials"]} if layer["materials"] else None
        p["names"] = names
        prep[i] = p
    return prep


class _State:
    """remember render settings, set new ones, put them all back (a projection render never leaks into the build)"""

    def __init__(self, pairs):
        self.pairs = pairs  # [(owner, attribute, value)]
        self.old = []

    def __enter__(self):
        # every old value FIRST, then the new ones: setting one changes another (an EXR format turns a PNG's 8-bit
        # depth into 16 before the depth's own turn — recorded then, 16 was "restored")
        self.old = [(owner, attr, getattr(owner, attr)) for owner, attr, _val in self.pairs]
        for owner, attr, val in self.pairs:
            setattr(owner, attr, val)
        return self

    def __exit__(self, *exc):
        # back in reverse, then again for whatever did not stick: Blender IGNORES (no error) a PNG's 8-bit depth while
        # the format is still EXR, and the format's change then leaves the depth at 16 — a 16-bit PNG output leaked
        # into the build broke every exact-colour render after it (the part-ID masks: every part_match garbage)
        for _pass in range(3):
            todo = [(o, a, v) for o, a, v in reversed(self.old) if _pass == 0 or _differs(o, a, v)]
            if not todo:
                break
            for owner, attr, val in todo:
                try:
                    setattr(owner, attr, val)
                except (TypeError, AttributeError, ValueError):
                    pass


def _differs(owner, attr, val):
    try:
        return getattr(owner, attr) != val
    except (AttributeError, ReferenceError):
        return False


def _camera(sc, bas, geom):
    import bpy  # noqa: PLC0415
    from mathutils import Matrix  # noqa: PLC0415

    d, r, u = bas
    rc = geom["r0"] + geom["w"] * geom["px"] / 2
    uc = geom["u0"] + geom["h"] * geom["px"] / 2
    loc = r * rc + u * uc + d * geom["d_cam"]
    cam = bpy.data.objects.new("KitProjectCam", bpy.data.cameras.new("KitProjectCam"))
    sc.collection.objects.link(cam)
    cam.data.type = "ORTHO"
    cam.data.sensor_fit = "AUTO"
    cam.data.ortho_scale = max(geom["w"], geom["h"]) * geom["px"]
    cam.data.clip_start = 1e-3
    cam.data.clip_end = geom["d_cam"] - geom["d_min"] + 10.0
    cam.matrix_world = Matrix(((r[0], u[0], d[0], loc[0]), (r[1], u[1], d[1], loc[1]), (r[2], u[2], d[2], loc[2]),
                               (0, 0, 0, 1)))
    return cam


def _override(kind):
    """the one material every object renders with: its world position, or its world normal (x (1 - pass_index): an
    object marked pass_index 1 renders as a zero normal)"""
    import bpy  # noqa: PLC0415

    mat = bpy.data.materials.new(f"{EXR_NAME}_{kind}")
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    em = nt.nodes.new("ShaderNodeEmission")
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    if kind == "position":
        nt.links.new(geo.outputs["Position"], em.inputs["Color"])
    else:
        info = nt.nodes.new("ShaderNodeObjectInfo")
        keep = nt.nodes.new("ShaderNodeMath")
        keep.operation = "SUBTRACT"
        keep.inputs[0].default_value = 1.0
        keep.use_clamp = True
        scale = nt.nodes.new("ShaderNodeVectorMath")
        scale.operation = "SCALE"
        nt.links.new(info.outputs["Object Index"], keep.inputs[1])
        nt.links.new(geo.outputs["Normal"], scale.inputs[0])
        nt.links.new(keep.outputs[0], scale.inputs["Scale"])
        nt.links.new(scale.outputs[0], em.inputs["Color"])
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    return mat


def render_override(asset, kind, bas, geom, hide=(), mark=()):
    """Cycles, 1 sample at each pixel's centre, every object in ONE emission material (its world position or normal),
    to a float EXR and back -> (rgb (h, w, 3), hit (h, w)) bottom row first"""
    import bpy  # noqa: PLC0415

    sc = asset.scene
    mat = _override(kind)
    cam = _camera(sc, bas, geom)
    fd, path = tempfile.mkstemp(prefix=f"{EXR_NAME}_", suffix=".exr")
    os.close(fd)
    hidden = [o for o in hide if _alive(o) and not o.hide_render]
    marked = [(o, o.pass_index) for o in mark if _alive(o)]
    ims = sc.render.image_settings
    pairs = [(sc.render, "engine", "CYCLES"), (sc.cycles, "device", "CPU"), (sc.cycles, "samples", 1),
             (sc.cycles, "use_denoising", False), (sc.cycles, "use_adaptive_sampling", False),
             (sc.cycles, "filter_width", 0.01), (sc.cycles, "film_exposure", 1.0),
             (sc.cycles, "sample_clamp_direct", 0.0), (sc.render, "film_transparent", True),
             (sc.render, "resolution_x", geom["w"]), (sc.render, "resolution_y", geom["h"]),
             (sc.render, "resolution_percentage", 100), (sc.render, "pixel_aspect_x", 1.0),
             (sc.render, "pixel_aspect_y", 1.0), (sc.render, "use_border", False), (sc, "camera", cam),
             (sc.render, "filepath", path), (ims, "file_format", "OPEN_EXR"), (ims, "color_mode", "RGBA"),
             (ims, "color_depth", "32")] + [(vl, "material_override", mat) for vl in sc.view_layers]
    try:
        for o in hidden:
            o.hide_render = True
        for o, _ in marked:
            o.pass_index = 1
        with _State(pairs):
            bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(path, check_existing=False)
        arr = np.empty(geom["w"] * geom["h"] * 4, np.float32)
        img.pixels.foreach_get(arr)
        bpy.data.images.remove(img)
        arr = arr.reshape(geom["h"], geom["w"], 4)
        return arr[..., :3].astype(np.float64), arr[..., 3] > 0.5
    finally:
        for o in hidden:
            o.hide_render = False
        for o, idx in marked:
            o.pass_index = idx
        bpy.data.objects.remove(cam)
        bpy.data.materials.remove(mat)
        try:
            os.remove(path)
        except OSError:
            pass


def helper_bakes(asset, obj, mat_index):
    """per texel of obj's map: world position, unit world normal, part index ("kit_part"), material index, and which
    texels hold a surface (the bake's margins average with the cleared background: divided back out by the coverage
    channel) -> (pos (H, W, 3), nrm, part (H, W) int, mat int, cover (H, W) 0..1)"""
    import bpy  # noqa: PLC0415

    tex = asset.tex
    out = {}

    def emit(build):
        def setup(nt, bsdf, o, mat):
            em = nt.nodes.new("ShaderNodeEmission")
            made = build(nt, mat)
            nt.links.new(made[-1].outputs[0], em.inputs["Color"])
            old = o.inputs["Surface"].links[0].from_socket
            nt.links.new(em.outputs["Emission"], o.inputs["Surface"])
            return made + [em], (old, o.inputs["Surface"])

        return setup

    def geom_out(socket):
        def build(nt, mat):
            g = nt.nodes.new("ShaderNodeNewGeometry")
            sep = nt.nodes.new("ShaderNodeVectorMath")  # (a pass-through: outputs[0] is the vector)
            sep.operation = "ADD"
            nt.links.new(g.outputs[socket], sep.inputs[0])
            return [g, sep]

        return build

    def ids(nt, mat):
        attr = nt.nodes.new("ShaderNodeAttribute")
        attr.attribute_name = "kit_part"
        comb = nt.nodes.new("ShaderNodeCombineColor")
        nt.links.new(attr.outputs["Fac"], comb.inputs[0])
        comb.inputs[1].default_value = float(mat_index.get(mat.name, -1))
        comb.inputs[2].default_value = 1.0
        return [attr, comb]

    for name, build in (("pos", geom_out("Position")), ("nrm", geom_out("Normal")), ("ids", ids)):
        img = bpy.data.images.new(f"{obj.name}_{EXR_NAME}_{name}", tex, tex, alpha=False, float_buffer=True)
        img.colorspace_settings.name = "Non-Color"
        try:
            asset._bake_pass(obj, img, "EMIT", 1, emit(build))
            a = np.empty(tex * tex * 4, np.float32)
            img.pixels.foreach_get(a)
            out[name] = a.reshape(tex, tex, 4)[..., :3].astype(np.float64)
        finally:
            bpy.data.images.remove(img)
    cover = np.clip(out["ids"][..., 2], 0, 1)
    f = np.maximum(cover, 1e-6)[..., None]
    pos = out["pos"] / f
    nrm = out["nrm"]
    nrm = nrm / np.maximum(np.linalg.norm(nrm, axis=-1, keepdims=True), 1e-9)
    part = np.rint(out["ids"][..., 0] / f[..., 0]).astype(np.int64)
    mat = np.rint(out["ids"][..., 1] / f[..., 0]).astype(np.int64)
    return pos, nrm, part, mat, cover


def _hide_list(asset):
    out = [o for o, _g in asset._floater_parts]
    if getattr(asset, "_high", None) is not None:
        out.append(asset._high)
    out += list((getattr(asset, "_opt_high", None) or {}).values())
    return [o for o in out if _alive(o)]


def paint(asset, obj, group, color, normal=None):
    """BAKE TIME: every layer that reaches this group, composited into its colour map (color (H, W, 3), sRGB 0..1,
    Blender's row order); a detail layer's bump= into the tangent normal map `normal` (H, W, 3+, 0..1: changed in
    place) -> (color, facts {layer index: counts}, whether the normal map changed)"""
    prep = asset._proj_prep
    mine = [i for i, layer in enumerate(asset.projections) if group not in layer["ignore"] and prep[i]["cams"]]
    if not mine:
        return color, {}, False
    high, asset._high = asset._high, None  # (the helper bakes read the low itself, never selected-to-active)
    try:
        mats = [m for m in obj.data.materials]
        mat_index = {m.name: k for k, m in enumerate(mats) if m}
        pos, nrm, part, mat, cover = helper_bakes(asset, obj, mat_index)
        hide = _hide_list(asset) + ([high] if high is not None else [])
        valid = cover > 1e-3
        idx = np.nonzero(valid.ravel())[0]
        P, N = pos.reshape(-1, 3)[idx], nrm.reshape(-1, 3)[idx]
        real = cover.ravel()[idx] > 0.999  # (facts count real texels; margins are painted too: no seams)
        pidx, midx = part.ravel()[idx], mat.ravel()[idx]
        names = list(obj.get("kit_parts", [])) or [obj.name]
        base = color.reshape(-1, 3)[idx].astype(np.float64)
        diag = float(np.linalg.norm(P.max(0) - P.min(0))) if len(P) else 1.0
        res_long = visibility_res(asset.tex)
        depth_cache, layers, decals, facts, samples, bumps = {}, [], [], {}, {}, []
        for i in mine:
            layer, p = asset.projections[i], prep[i]
            allow = np.ones(len(idx), bool)
            if layer["parts"]:
                want = set(layer["parts"])
                ok_part = np.array([n in want or n.split("~")[0] in want for n in names] + [False])
                allow &= ok_part[np.clip(pidx, -1, len(names) - 1)]
            if p["mats"] is not None:
                ok_mat = np.array([bool(m and m.name in p["mats"]) for m in mats] + [False])
                allow &= ok_mat[np.clip(midx, -1, len(mats) - 1)]
            f = facts.setdefault(i, {"seen": 0, "covered": 0, "backdrop": 0, "diff_sum": 0.0, "diff_n": 0,
                                     "painted": 0})
            for key, flip in passes(layer):
                cam = p["cams"][key]
                ck = (key, tuple(round(e, 6) for e in cam["ext"]))  # (another ignore= frames another box)
                if ck not in depth_cache:
                    geom = view_geometry(cam["ext"], cam["depth"], res_long)
                    rgb, hit = render_override(asset, "position", cam["bas"], geom, hide=hide)
                    depth_cache[ck] = (rgb @ cam["bas"][0], hit, geom)
                depth, hit, geom = depth_cache[ck]
                vis = visible(P, N, cam["bas"], depth, hit, geom, tol=1e-4 * diag + 1e-5)
                c = np.abs(N @ cam["bas"][0])
                face = ramp(c, *layer["facing"])
                w = face * vis * allow
                a, b = to_ab(P, cam["bas"], cam["ext"])
                if flip:
                    a = 1 - a
                seen = (w > 0) & real
                f["seen"] += int(seen.sum())
                live = np.nonzero(w > 0)[0]
                if layer["kind"] == "decal":
                    rgb_d, wd = sample_decal(p["patch"], p["rect"], a[live], b[live], layer["feather"])
                    wfull = np.zeros(len(idx))
                    wfull[live] = w[live] * wd * layer["mix"]
                    col = np.zeros((len(idx), 3))
                    col[live] = rgb_d
                    decals.append((col, wfull))
                    f["painted"] += int(((wfull > 0.5) & real).sum())
                    continue
                X, Y = to_picture(a[live], b[live], p["fr"])
                Xc, Yc = X - p["off"][0], Y - p["off"][1]
                soft = bilinear(p["soft"], Xc, Yc)
                wfull = np.zeros(len(idx))
                wfull[live] = w[live] * soft * layer["mix"]
                col = np.zeros((len(idx), 3))
                dmod = None
                if layer["kind"] == "project" and layer.get("detail") and p.get("detail") is not None:
                    # detail mode: the texel keeps its material's colour, times the picture's fine structure
                    sig = bilinear(p["detail"]["signal"], Xc, Yc)
                    dmod = np.zeros(len(idx))
                    dmod[live] = layer["detail"] * DETAIL_GAIN * sig
                    col[live] = modulate(base[live], dmod[live])
                    if layer["bump"] > 0:
                        hgt = np.zeros(len(idx))
                        hgt[live] = layer["bump"] * sig
                        bumps.append((hgt, wfull, c))
                else:
                    col[live] = bilinear(p["img"][..., :3], Xc, Yc)
                    if layer.get("relief") and p.get("detail") is not None:  # (colour mode's relief=)
                        hgt = np.zeros(len(idx))
                        sig = bilinear(p["detail"]["signal"], Xc, Yc)
                        if p["detail"].get("shape") is not None:  # (its lines 40 %, its sculpted shape 60 %)
                            sig = 0.4 * sig + 0.6 * bilinear(p["detail"]["shape"], Xc, Yc)
                        hgt[live] = layer["relief"] * sig
                        bumps.append((hgt, wfull, c))
                layers.append((col, wfull, c))
                samples.setdefault(i, []).append((col, wfull, c, dmod))
                cov = (wfull > 0) & real
                f["covered"] += int(cov.sum())
                if p["obj"] is not None:
                    inside = live[soft > 0]
                    Xi = np.clip((X[soft > 0] - p["off"][0]).astype(np.int64), 0, p["obj"].shape[1] - 1)
                    Yi = np.clip((Y[soft > 0] - p["off"][1]).astype(np.int64), 0, p["obj"].shape[0] - 1)
                    on_bg = ~p["obj"][Yi, Xi]
                    f["backdrop"] += int((on_bg & real[inside]).sum())
        out, alpha = blend(base, layers, decals)
        base_m = match_to_pictures(base, out, alpha, midx, mats, real,
                                   {v["mat"].name for v in asset.mats.values() if v.get("imported")})
        if base_m is not None:   # (a generated surface's own paint, matched to its photos: no patches where they end)
            base = base_m
            out, alpha = blend(base, layers, decals)
        tot = sum(w_ * c_ ** BLEND_POWER for _x, w_, c_ in layers) if layers else np.zeros(len(idx))
        dec_w = np.zeros(len(idx))
        for _c, wd in decals:
            dec_w = np.maximum(dec_w, wd)
        luma = np.array([0.2126, 0.7152, 0.0722])
        user = prep[mine[0]]["names"]
        for i, lst in samples.items():
            for col, wfull, c, dmod in lst:
                # where ONE picture is all of a texel (full weight, the squarest view by far, no decal on it): the map
                # must hold that picture's colour (sanity), and what it did to each material's colour is measured
                share = wfull * c ** BLEND_POWER
                sel = (wfull >= 0.999) & (alpha >= 0.999) & (share >= 0.98 * np.maximum(tot, 1e-12)) & (dec_w <= 0) \
                    & real
                if not sel.any():
                    continue
                facts[i]["diff_sum"] += float(np.abs(out[sel] - col[sel]).mean(1).sum() * 255)
                facts[i]["diff_n"] += int(sel.sum())
                shift = (out[sel] - base[sel]) @ luma * 255
                by_mat = facts[i].setdefault("materials", {})
                for k in np.unique(midx[sel]):
                    m_ = mats[k] if 0 <= k < len(mats) else None
                    nm = user.get(m_.name, m_.name) if m_ else "?"
                    one = midx[sel] == k
                    s_ = by_mat.setdefault(nm, [0.0, 0])
                    s_[0] += float(shift[one].sum())
                    s_[1] += int(one.sum())
                if dmod is not None:
                    facts[i]["mod_sum"] = facts[i].get("mod_sum", 0.0) + float(dmod[sel].sum())
                    facts[i]["mod_sq"] = facts[i].get("mod_sq", 0.0) + float((dmod[sel] ** 2).sum())
                    facts[i]["mod_n"] = facts[i].get("mod_n", 0) + int(sel.sum())
        bumped = False
        if bumps and normal is not None:
            # the detail as relief: its height (blended like the colour) -> UV-space slope -> the tangent normal map
            num = sum(h_ * w_ * c_ ** BLEND_POWER for h_, w_, c_ in bumps)
            hgt = np.where(tot > 1e-12, num / np.maximum(tot, 1e-12), 0.0) * alpha
            grid = np.zeros(valid.shape)
            grid.ravel()[idx] = hgt
            gx, gy = texel_slope(grid, valid, pos)
            tilt = (np.abs(gx) + np.abs(gy)) > 1e-6  # (every other texel keeps its normal byte for byte)
            normal[tilt, :3] = apply_bump(normal[..., :3], gx, gy, 1.0)[tilt]
            bumped = bool(tilt.any())
            for i in mine:
                if asset.projections[i].get("bump") or asset.projections[i].get("relief"):
                    facts[i]["bumped"] = int((np.hypot(gx, gy).ravel()[idx][real] > 0.05).sum())  # (tilted > ~3 deg)
        flat = color.reshape(-1, 3)
        flat[idx] = np.clip(out, 0, 1)
        return flat.reshape(color.shape), facts, bumped
    finally:
        asset._high = high


def render_colour(asset, objs, bas, geom, path):
    """Workbench, flat, the baked colour maps as the game holds them, no anti-aliasing -> (H, W, 4) bottom row first"""
    import bpy  # noqa: PLC0415

    sc = asset.scene
    sh = sc.display.shading
    cam = _camera(sc, bas, geom)
    for o in objs:
        for m in o.data.materials:
            if m and m.node_tree:
                for nd in m.node_tree.nodes:
                    if nd.type == "TEX_IMAGE" and nd.image and nd.image.name.endswith("_color"):
                        m.node_tree.nodes.active = nd
    hidden = [o for o in sc.objects if o.type == "MESH" and o not in objs and not o.hide_render]
    ims = sc.render.image_settings
    pairs = [(sc.render, "engine", "BLENDER_WORKBENCH"), (sc.view_settings, "view_transform", "Standard"),
             (sc.view_settings, "look", "None"), (sc.view_settings, "exposure", 0.0),
             (sc.view_settings, "gamma", 1.0), (sc.render, "film_transparent", True),
             (sh, "light", "FLAT"), (sh, "color_type", "TEXTURE"), (sh, "show_cavity", False),
             (sh, "show_object_outline", False), (sh, "show_xray", False), (sh, "show_shadows", False),
             (sc.display, "render_aa", "OFF"), (sc.render, "resolution_x", geom["w"]),
             (sc.render, "resolution_y", geom["h"]), (sc.render, "resolution_percentage", 100),
             (sc.render, "use_border", False), (sc, "camera", cam), (sc.render, "filepath", path),
             (ims, "file_format", "PNG"), (ims, "color_mode", "RGBA"), (ims, "color_depth", "8")]
    try:
        for o in hidden:
            o.hide_render = True
        with _State(pairs):
            bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(path, check_existing=False)
        arr = np.empty(geom["w"] * geom["h"] * 4, np.float32)
        img.pixels.foreach_get(arr)
        bpy.data.images.remove(img)
        return arr.reshape(geom["h"], geom["w"], 4).astype(np.float64)
    finally:
        for o in hidden:
            o.hide_render = False
        bpy.data.objects.remove(cam)


def seen_from_view(asset, objs, layer, p, key, flip, renders):
    """THE CHECK: the finished model seen flat from the picture's camera against the picture itself, cell by cell,
    where the picture should be all there is (|n.v| >= 0.9, well inside the outline, not under a decal) — an
    end-to-end proof that the map holds the picture where the picture is (a mirrored or shifted projection, a wrong
    frame, a colour-space slip all show here) -> facts (+ an evidence sheet: the picture above, the model below)"""
    cam = p["cams"][key]
    geom = view_geometry(cam["ext"], cam["depth"], 1024)
    shown = [o for g, o in objs.items() if g not in layer["ignore"]]
    others = [o for g, o in objs.items() if g in layer["ignore"]]
    fd, tmp = tempfile.mkstemp(prefix=f"{EXR_NAME}_", suffix=".png")
    os.close(fd)
    try:
        model = render_colour(asset, list(objs.values()), cam["bas"], geom, tmp)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    rest = [o for o in asset.scene.objects if o.type == "MESH" and o not in objs.values()]
    nrm, hit = render_override(asset, "normal", cam["bas"], geom, hide=rest, mark=others)
    h, w = geom["h"], geom["w"]
    jj, ii = np.meshgrid(np.arange(w) + 0.5, np.arange(h) + 0.5)
    rr, uu = geom["r0"] + jj * geom["px"], geom["u0"] + ii * geom["px"]
    rmin, rmax, umin, umax = cam["ext"][:4]
    a = (rr - rmin) / max(rmax - rmin, 1e-9)
    b = (uu - umin) / max(umax - umin, 1e-9)
    if flip:
        a = 1 - a
    X, Y = to_picture(a, b, p["fr"])
    Xc, Yc = (X - p["off"][0]).ravel(), (Y - p["off"][1]).ravel()
    pic = bilinear(p["img"][..., :3], Xc, Yc).reshape(h, w, 3)
    dist = bilinear(p["dist"], Xc, Yc).reshape(h, w)
    alpha = bilinear(p["img"][..., 3], Xc, Yc).reshape(h, w)
    nl = np.linalg.norm(nrm, axis=-1)
    c = np.abs(nrm @ cam["bas"][0]) / np.maximum(nl, 1e-9)
    body = hit & (model[..., 3] > 0.5) & (nl > 0.5)  # (a marked = ignored group renders a zero normal)
    core = inside_distance(body, 3) > 2
    sel = core & (c >= 0.9) & (dist >= layer["feather"] + 1.5) & (alpha >= 0.99)
    for j, other in enumerate(asset.projections):  # under a decal of this camera the picture is not the colour
        if other["kind"] == "decal" and passes(other)[0][0] == key and j in asset._proj_prep:
            a0, a1, b0, b1 = asset._proj_prep[j]["rect"]
            sel &= ~((a >= a0) & (a <= a1) & (b >= b0) & (b <= b1))
    detail = None
    if layer.get("detail") and p.get("detail") is not None:
        # detail mode: the colours differ by design (the material's) — compare FINE STRUCTURE to fine structure: the
        # same extraction of log luminance (its radii in this render's pixels) on the model and on the picture
        dd = p["detail"]
        ppr = geom["px"] * p["fr"][2] / max(rmax - rmin, 1e-9)  # picture px per render px
        r_lo = 0.5 * dd["px_per_texel"] / ppr if dd["px_per_texel"] / ppr >= 2 else 0.0
        r_hi = min(max(dd["r_hi"] / ppr, r_lo + 2.0), 32.0)
        m_ = body & (dist > layer["feather"])
        bm = fine_structure(log_luminance(model[..., :3]), m_, r_lo, r_hi)
        bp = fine_structure(log_luminance(pic), m_, r_lo, r_hi)
        if sel.sum() < 50 or float(bp[sel].std()) < 0.01:
            detail = {"note": "not compared: the picture shows no fine structure where the model faces it"}
        else:
            detail = {"correlation": round(pearson(bm[sel], bp[sel]), 3), "px": int(sel.sum())}
    hr = p["fr"][3]
    rows = max(1, int(round(8 * hr))) if hr < 1 else 8
    cols = 8 if hr < 1 else max(1, int(round(8 / hr)))
    if detail is not None:
        cells, off = [], []
        if detail.get("correlation", 1.0) < 0.3:
            off = [f"its fine structure correlates {detail['correlation']:.2f} with the picture's (want >= 0.30)"]
    else:
        cells = cells_compare(a[sel], b[sel], model[..., :3][sel], pic[sel], cols, rows) if sel.sum() else []
        off = [x for x in cells if x["delta_e"] > 10]
    # the evidence: the picture as this camera frames it (above), the model's map seen from there (below)
    sheet = np.zeros((2 * h, w, 4), np.float32)
    sheet[..., 3] = 1
    inside = dist > 0
    sheet[:h, :, :3] = np.where(inside[..., None], pic, 0.12)[::-1]
    sheet[h:, :, :3] = np.where(body[..., None], model[..., :3], 0.12)[::-1]
    side = "" if not flip else "_mirror"
    out = os.path.join(renders, f"{asset.name}_project_{layer['name']}{side}.png")
    save_picture(sheet, out)
    if detail is not None:
        return {"fine_structure": detail, "off": off, "sheet": out.replace("\\", "/")}
    worst = max(cells, key=lambda x: x["delta_e"]) if cells else None
    diff = float(np.abs(model[..., :3][sel] - pic[sel]).mean() * 255) if sel.sum() else None
    return {"cells": len(cells), "off": [f"u {x['a'][0]:.2f}-{x['a'][1]:.2f} h {x['b'][0]:.2f}-{x['b'][1]:.2f}: "
                                         f"dE {x['delta_e']}" for x in sorted(off, key=lambda x: -x["delta_e"])[:4]],
            "worst_delta_e": worst["delta_e"] if worst else None,
            "mean_diff_255": round(diff, 1) if diff is not None else None, "px": int(sel.sum()),
            "sheet": out.replace("\\", "/")}


def report(asset, objs, renders, geo=False):
    """after build: per layer, what it painted (texels the view sees, covered, on the picture's backdrop, the map
    against the picture), whether its picture is where its trace says, and the model seen from its camera ->
    (facts, checks)"""
    import rbx_critic  # noqa: PLC0415

    rows, checks = [], []
    misaligned, thin, unmatched, lost, detail_bad = [], [], [], [], []
    for i, layer in enumerate(asset.projections):
        p = asset._proj_prep[i]
        row = {"name": layer["name"], "kind": layer["kind"], "view": layer["view"], "picture": layer["picture"],
               "mix": layer["mix"]}
        if layer["mirror"]:
            row["mirror"] = True
        if layer["kind"] == "project":
            row["alignment"] = al = p["align"]
            if misplaced(al, p["fr"][2]):
                dx, dy = al["shift_px"]
                where = ", ".join(s for s in (f"{abs(dx)} px {'right' if dx > 0 else 'left'}" if dx else "",
                                              f"{abs(dy)} px {'down' if dy > 0 else 'up'}" if dy else "") if s)
                misaligned.append(f"{layer['name']}: the picture's object sits {where} of where its trace says "
                                  f"({al['outline_on_backdrop_pct']}% of the traced outline shows the backdrop; "
                                  f"moved, the outline would match it {al['iou_if_shifted']:.0%} not {al['iou']:.0%})")
        if not geo:
            tot = {"seen": 0, "covered": 0, "backdrop": 0, "diff_sum": 0.0, "diff_n": 0, "painted": 0}
            by_mat = {}
            for g_facts in asset._proj_facts.values():
                for k, v in ((g_facts or {}).get(str(i)) or (g_facts or {}).get(i) or {}).items():
                    if k == "materials":
                        for nm, (s_, n_) in v.items():
                            acc = by_mat.setdefault(nm, [0.0, 0])
                            acc[0] += s_
                            acc[1] += n_
                    else:
                        tot[k] = tot.get(k, 0) + v
            row["texels_seen"] = tot["seen"]
            if layer.get("relief"):  # (colour mode's relief=: the picture's fine structure in the normal map)
                row["relief"] = {"strength": layer["relief"], "bumped_texels": tot.get("bumped", 0)}
            if by_mat:  # how the picture moved each material's colour (mean luma, /255; - = darker)
                row["material_shift_255"] = {nm: round(s_ / n_, 1) for nm, (s_, n_) in by_mat.items() if n_}
            if layer.get("detail") and tot.get("mod_n"):
                mean = tot["mod_sum"] / tot["mod_n"]
                std = math.sqrt(max(tot["mod_sq"] / tot["mod_n"] - mean * mean, 0.0))
                dd = p.get("detail") or {}
                row["detail"] = {"strength": layer["detail"], "contrast_pct": round(100 * std, 2),
                                 "mean_change_pct": round(100 * mean, 2),
                                 # (its strongest fine features — the 98th percentile — are this much darker than
                                 # what is around them: the scale the picture's signal was divided by)
                                 "picture_fine_contrast_pct": round(100 * (1 - math.exp(-dd.get("scale", 0.0))), 1),
                                 "radii_px": [round(dd.get("r_lo", 0.0), 2), round(dd.get("r_hi", 0.0), 2)],
                                 "picture_px_per_texel": round(dd.get("px_per_texel", 0.0), 2),
                                 **({"bumped_texels": tot.get("bumped", 0)} if layer.get("bump") or layer.get("relief") else {})}
                shifted = {nm: v for nm, v in row.get("material_shift_255", {}).items() if abs(v) > 4.0}
                if std < 0.005:
                    detail_bad.append(f"{layer['name']}: {100 * std:.2f}% contrast transferred — the picture shows "
                                      f"no thin features up to ~{2 * dd.get('r_hi', 0):.0f} px wide (raise "
                                      "detail_px=, or use the colour mode)")
                if shifted:
                    moved = ", ".join(f"{k} {v:+.1f}/255" for k, v in shifted.items())
                    detail_bad.append(f"{layer['name']}: moved {moved} — detail mode keeps the material's colour; "
                                      "lower detail= (a picture of mostly dark lines is cut by the clamp)")
            if layer["kind"] == "decal":
                row["texels_painted"] = tot["painted"]
                if tot["painted"] == 0:
                    lost.append(f"{layer['name']} (the {layer['view']} view sees nothing of the model at its place)")
            else:
                cov = 100 * tot["covered"] / max(1, tot["seen"])
                row["covered_pct"] = round(cov, 1)
                row["on_backdrop_pct"] = round(100 * tot["backdrop"] / max(1, tot["covered"]), 1)
                row["map_vs_picture_255"] = round(tot["diff_sum"] / tot["diff_n"], 2) if tot["diff_n"] else None
                if tot["seen"] == 0 or cov < 80:
                    thin.append(f"{layer['name']}: {cov:.0f}% of the {tot['seen']} texels its view sees")
                if layer["mix"] >= 0.99 and not layer["parts"] and not layer["materials"] and p["cams"]:
                    for key, flip in passes(layer):
                        s = seen_from_view(asset, objs, layer, p, key, flip, renders)
                        row["seen_from_" + layer["view"] + ("_mirror" if flip else "")] = s
                        if s.get("off"):
                            unmatched.append(f"{layer['name']}{' (mirror)' if flip else ''}: {'; '.join(s['off'][:3])}"
                                             f" — {s['sheet']}")
                else:
                    row["seen_from_view"] = "not checked: mix < 1 or a parts / materials filter (the map is meant " \
                                            "to differ from the picture there)"
        rows.append(row)
    if misaligned:
        checks.append(rbx_critic._check(
            "projection_alignment", False, misaligned[:4], "the picture's object where its trace's frame says",
            "a projected picture is not where its trace says: " + "; ".join(misaligned[:3]) + " — the trace was made "
            "on another crop or version of the picture, or the picture changed since: re-run kit trace on the picture "
            "the projection paints with (its colours land shifted on the model)", "warn"))
    if thin and not geo:
        checks.append(rbx_critic._check(
            "projection_coverage", False, thin[:4], ">= 80% of what each view sees lands inside its traced outline",
            "a picture paints little of what its view sees: " + "; ".join(thin[:3]) + " — the model's silhouette "
            "differs from the trace there (see reference_<view>: IoU and the diff image), or ignore= is missing the "
            "groups the picture does not show; those texels keep the material's colour", "warn"))
    if unmatched:
        checks.append(rbx_critic._check(
            "projection_match", False, unmatched[:4], "seen from its camera the model shows its picture (dE <= 10)",
            "seen from a picture's own camera the finished map differs from the picture: " + "; ".join(unmatched[:2])
            + " — another picture or decal paints over it, or the map is too small for the picture's detail (raise "
            "tex=); if neither, the projection itself is wrong: look at the sheet (the picture above, the model "
            "below)", "warn"))
    if detail_bad and not geo:
        checks.append(rbx_critic._check(
            "projection_detail", False, detail_bad[:4], "detail mode: fine structure transferred, colours kept "
            "(each material's mean within 4/255)", "a detail projection did not do its job: " + "; ".join(
                detail_bad[:3]), "warn"))
    if lost and not geo:
        checks.append(rbx_critic._check(
            "projection_decal", False, lost[:4], "every decal lands on the model",
            "a decal painted nothing: " + "; ".join(lost[:3]) + " — check at= / size= (the trace's design units: u 0 "
            "back .. 1 front, h up, in lengths) and its view (a decal paints what that camera sees first)", "warn"))
    return {"layers": rows}, checks
