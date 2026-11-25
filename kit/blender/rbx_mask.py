"""A MASK THE AUTHOR PLACES (the owner's method lists, 2026-11-13: "texture painting", "hand-painted textures",
"masks", "material masks", "material blending"; the 3D methods audit, stage S3: "masks from the mesh's maps; none
painted" / "layers over a base; no blend between two material zones").

The kit's layers lie where the MESH says - edges, cavities, what faces up. A texture artist also paints where a
thing goes because the design says so: the scorch round a muzzle, a painted stripe, moss up the north side, a
second material over half a blade. A placed mask is that: a number 0..1 for every point of the surface, from
  a PICTURE   looked at from the front, the side or above and laid over the model's box - where the picture is
              light (or has alpha) the mask is on, its greys a soft edge; or
  a RULE      on the point itself (x, y, z in the model's frame): lambda p: p[1] > 2.0, or a number 0..1.
A layer of a material's stack then names it (rbx.layer("rust", where="mask:scorch", amount=1, breakup=0)).
Pure numpy: the build gives the points under the map's texels; no Blender."""

import numpy as np

VIEWS = ("front", "side", "top")
EDGE = 1e-4   # how far past the picture's border (of its width) a point still takes it


def view_frame(lo, hi, view="front"):
    """the frame a picture is laid by, over a box lo..hi (the model's frame: x right, y up, z toward the viewer's
    back when looked at from the front) -> (origin: the picture's lower left, across, up, width, height).
    front: looked at from -z (the model's +x on the viewer's LEFT); side: from +x; top: from above, the model's
    front (-z) at the picture's bottom."""
    lo, hi = np.asarray(lo, float), np.asarray(hi, float)
    if view == "front":
        return (np.array([hi[0], lo[1], lo[2]]), np.array([-1.0, 0, 0]), np.array([0, 1.0, 0]),
                float(hi[0] - lo[0]), float(hi[1] - lo[1]))
    if view == "side":
        return (np.array([hi[0], lo[1], hi[2]]), np.array([0, 0, -1.0]), np.array([0, 1.0, 0]),
                float(hi[2] - lo[2]), float(hi[1] - lo[1]))
    if view == "top":
        return (np.array([hi[0], hi[1], lo[2]]), np.array([-1.0, 0, 0]), np.array([0, 0, 1.0]),
                float(hi[0] - lo[0]), float(hi[2] - lo[2]))
    raise ValueError(f'view="{view}" - one of {", ".join(VIEWS)}')


def sample(pts, picture, frame):
    """a picture's value at points of space: each point is dropped straight onto the picture's plane (every depth
    behind it takes the same value - the far side of the model too). picture: (H, W) 0..1, row 0 its TOP.
    -> (N,) 0..1, between its texels; a point outside the picture is 0."""
    origin, across, up, width, height = frame
    pts = np.asarray(pts, float)
    pic = np.asarray(picture, float)
    h, w = pic.shape[:2]
    if len(pts) == 0 or width <= 0 or height <= 0:
        return np.zeros(len(pts))
    fx_, fy_ = (pts - origin) @ across / width, (pts - origin) @ up / height
    # (a face lying ON the picture's border - a box's own sides, looked at from the front - is inside: the review
    # found an all-white picture leaving them bare, by the noise of a float)
    inside = (fx_ > -EDGE) & (fx_ < 1 + EDGE) & (fy_ > -EDGE) & (fy_ < 1 + EDGE)
    x = fx_ * w - 0.5
    y = (1.0 - fy_) * h - 0.5
    x, y = np.clip(x, 0, w - 1), np.clip(y, 0, h - 1)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    x1, y1 = np.minimum(x0 + 1, w - 1), np.minimum(y0 + 1, h - 1)
    fx, fy = x - x0, y - y0
    v = (pic[y0, x0] * (1 - fx) * (1 - fy) + pic[y0, x1] * fx * (1 - fy)
         + pic[y1, x0] * (1 - fx) * fy + pic[y1, x1] * fx * fy)
    return np.where(inside, np.clip(v, 0, 1), 0.0)


def by_rule(pts, rule):
    """a rule on the point -> (N,) 0..1 (True / False, or a number that is held to 0..1)"""
    return np.array([float(np.clip(float(rule(tuple(p))), 0.0, 1.0)) for p in np.asarray(pts, float)])


REACH = 8   # texels a mask is carried past the edge of the texels it was asked on (the islands' margins)


def to_map(n, rows, cols, values, reach=REACH, others=None):
    """the values of the covered texels on an n x n map -> (n, n, 1) float32. A texel nobody asked takes the mean
    of its asked neighbours, `reach` texels out from every island (the layer is drawn into the islands' margins
    as the bake draws its colour there: without it a stripe shows a notch at every seam); further out it is 0.
    others: (rows, cols) of texels that belong to surface the mask is NOT asked on (the group's other parts):
    they stay 0 and nothing is carried onto them."""
    out = np.zeros((n, n), np.float32)
    known = np.zeros((n, n), bool)
    blocked = np.zeros((n, n), bool)   # (other parts' texels: never filled, and nothing is read from them)
    if others is not None and len(others[0]):
        blocked[np.asarray(others[0], int), np.asarray(others[1], int)] = True
    if len(rows):
        r, c = np.asarray(rows, int), np.asarray(cols, int)
        out[r, c] = np.asarray(values, np.float32)
        known[r, c] = True
        blocked[r, c] = False
    for _ in range(int(reach)):
        if (known | blocked).all() or not known.any():
            break
        total = np.zeros((n, n), np.float32)
        count = np.zeros((n, n), np.float32)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            v, k = np.roll(out * known, (dy, dx), axis=(0, 1)), np.roll(known, (dy, dx), axis=(0, 1))
            if dy == 1:
                k[0] = False
            elif dy == -1:
                k[-1] = False
            elif dx == 1:
                k[:, 0] = False
            else:
                k[:, -1] = False
            total += np.where(k, v, 0.0)
            count += k
        fresh = (~known) & (~blocked) & (count > 0)
        out[fresh] = total[fresh] / count[fresh]
        known |= fresh
    return out[..., None]


def said(values, area=None):
    """how much of the asked surface a mask is on -> {"on": the share over half, "mean": its mean} - by SURFACE when
    each value's area is given (a texel of a part laid denser covers less of it: counted by texels, the share leaned
    toward the densely laid parts - card yp3e), else by texels"""
    v = np.asarray(values, float)
    if len(v) == 0:
        return {"on": 0.0, "mean": 0.0}
    w = np.ones_like(v) if area is None else np.asarray(area, float)
    tot = float(w.sum()) or 1.0
    return {"on": round(float(w[v > 0.5].sum() / tot), 4), "mean": round(float((v * w).sum() / tot), 4)}


def picture_values(px):
    """a mask's picture (H, W, 4) 0..1 -> (H, W) 0..1: its ALPHA when the picture really uses it (some of it clear
    and some solid: at least ALPHA_SHARE of its pixels each - one half-clear pixel was read as an alpha mask,
    card yp3e), else how LIGHT it is"""
    a = np.asarray(px, float)
    alpha = a[..., 3]
    if float((alpha < 0.5).mean()) >= ALPHA_SHARE and float((alpha >= 0.5).mean()) >= ALPHA_SHARE:
        return alpha
    return a[..., :3].mean(axis=2)


ALPHA_SHARE = 0.01   # a picture's alpha is its mask when this share of its pixels is clear and this share solid


# --- A BRUSH STROKE THAT FOLLOWS THE SURFACE (the audit, "texture painting": a picture is projected flat; "a brush
# that follows the surface round a corner is not built" - card yp3e). The distance is taken ALONG the surface, over
# the map's own texels (each one a point of the model): within an island from texel to texel, and across a seam
# where two islands' border texels lie together on the model. A stroke round a box's edge paints both faces as far
# as its radius reaches over the edge - not through the box to the far side, as a picture laid over it does.
STROKE_STEP = 0.125   # a stroke is sampled every this share of its radius
STROKE_OFF = 1.0      # a stroke's point further off the model than this share of its radius is refused


def _links(pos, act, idx, step_bar):
    """the texel-to-texel links of the active texels: 16 directions on the map, where their places lie no further
    apart than step_bar -> (a, b, length) index arrays into the active list"""
    n = act.shape[0]
    A, B, W = [], [], []
    # (the 8 neighbours and the knight's moves: 16 directions - with 8 alone a stroke's end came out an octagon)
    for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1), (1, 2), (2, 1), (2, -1), (1, -2)):
        r0, r1 = max(0, -dr), n - max(0, dr)
        c0, c1 = max(0, -dc), n - max(0, dc)
        a = act[r0:r1, c0:c1]
        b = act[r0 + dr:r1 + dr, c0 + dc:c1 + dc]
        both = a & b
        if not both.any():
            continue
        pa = pos[r0:r1, c0:c1][both]
        pb = pos[r0 + dr:r1 + dr, c0 + dc:c1 + dc][both]
        w = np.linalg.norm(pa - pb, axis=1)
        ok = w <= step_bar
        A.append(idx[r0:r1, c0:c1][both][ok])
        B.append(idx[r0 + dr:r1 + dr, c0 + dc:c1 + dc][both][ok])
        W.append(w[ok])
    if not A:
        return np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros(0)
    return np.concatenate(A), np.concatenate(B), np.concatenate(W)


def _seams(pos, border, idx, reach_d):
    """links ACROSS seams: border texels of the active set lying within reach_d of each other on the model (a cell
    hash; pairs that are neighbours on the map are linked already) -> (a, b, length)"""
    rr, cc = np.nonzero(border)
    if len(rr) < 2:
        return np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros(0)
    p = pos[rr, cc].astype(np.float64)
    ids = idx[rr, cc]
    cell = np.floor(p / reach_d).astype(np.int64)
    base = cell.min(axis=0)
    cell -= base
    dim = cell.max(axis=0) + 3
    key = (cell[:, 0] + 1) * dim[1] * dim[2] + (cell[:, 1] + 1) * dim[2] + (cell[:, 2] + 1)
    order = np.argsort(key, kind="stable")
    ks = key[order]
    A, B, W = [], [], []
    for ox in (-1, 0, 1):
        for oy in (-1, 0, 1):
            for oz in (-1, 0, 1):
                want = key + ox * dim[1] * dim[2] + oy * dim[2] + oz
                lo = np.searchsorted(ks, want, "left")
                hi = np.searchsorted(ks, want, "right")
                most = int((hi - lo).max(initial=0))
                for k in range(most):
                    has = lo + k < hi
                    i = np.nonzero(has)[0]
                    j = order[lo[i] + k]
                    keep = i < j
                    i, j = i[keep], j[keep]
                    far = (np.abs(rr[i] - rr[j]) > 1) | (np.abs(cc[i] - cc[j]) > 1)
                    i, j = i[far], j[far]
                    w = np.linalg.norm(p[i] - p[j], axis=1)
                    ok = w <= reach_d
                    A.append(ids[i[ok]])
                    B.append(ids[j[ok]])
                    W.append(w[ok])
    return np.concatenate(A), np.concatenate(B), np.concatenate(W)


def stroke_distance(positions, inside, stroke, radius):
    """how far each texel lies from a brush stroke, ALONG the surface -> (n, n) float (inf beyond the radius and
    off the model). positions (n, n, 3) and inside (n, n): each texel's place (rbx_wear.uv_positions, pad=0);
    stroke: the points the brush passes through, in the positions' units; radius: how far it reaches (same)"""
    pos = np.asarray(positions, np.float64)
    ins = np.asarray(inside, bool)
    pts = np.asarray(stroke, np.float64).reshape(-1, 3)
    r = float(radius)
    out = np.full(ins.shape, np.inf)
    if not ins.any() or len(pts) == 0 or not r > 0:
        return out
    samples = [pts[0]]
    for a, b in zip(pts[:-1], pts[1:]):   # (the stroke sampled along its straight legs)
        k = max(1, int(np.ceil(np.linalg.norm(b - a) / (STROKE_STEP * r))))
        samples += [a + (b - a) * (t / k) for t in range(1, k + 1)]
    samples = np.array(samples)
    # only texels a straight line puts within the radius can be within it along the surface
    flat = pos[ins]
    near = np.full(len(flat), np.inf)
    nearest = []
    for sp in samples:
        d = np.linalg.norm(flat - sp, axis=1)
        near = np.minimum(near, d)
        nearest.append((int(np.argmin(d)), float(d.min())))
    off = max(d_ for _i, d_ in nearest)
    if off > STROKE_OFF * r:
        raise ValueError(f"a stroke passes {off:.1f} off the model (its radius is {r:.1f}): lay its points ON the "
                         "surface it paints")
    act = np.zeros(ins.shape, bool)
    act[ins] = near <= r
    rows, cols = np.nonzero(act)
    idx = -np.ones(ins.shape, np.int64)
    idx[rows, cols] = np.arange(len(rows))
    p_act = pos[rows, cols]
    full = np.zeros(ins.shape, bool)
    full[ins] = True
    # a texel's own size: the median link on the map
    a_, b_, w_ = _links(pos, act, idx, np.inf)
    texel = float(np.median(w_)) if len(w_) else 1.0
    a_, b_, w_ = _links(pos, act, idx, 6.0 * texel)
    pad = np.pad(full, 1)
    border = act & ~(pad[:-2, 1:-1] & pad[2:, 1:-1] & pad[1:-1, :-2] & pad[1:-1, 2:])
    sa, sb, sw = _seams(pos, border, idx, 2.0 * texel)
    A, B, W = np.concatenate([a_, sa]), np.concatenate([b_, sb]), np.concatenate([w_, sw])
    dist = np.full(len(rows), np.inf)
    where = {tuple(x) for x in zip(rows.tolist(), cols.tolist())}
    flat_rows, flat_cols = np.nonzero(ins)
    for (i, d0), _sp in zip(nearest, samples):
        rc = (int(flat_rows[i]), int(flat_cols[i]))
        if rc in where:
            j = idx[rc]
            dist[j] = min(dist[j], 0.0)   # (the stroke laid onto the surface where it is nearest)
    for _ in range(4 * len(rows) + 8):   # (relaxed until nothing moves: never more rounds than texels)
        was = dist.copy()
        np.minimum.at(dist, B, dist[A] + W)
        np.minimum.at(dist, A, dist[B] + W)
        if np.array_equal(was, dist):
            break
    dist[dist > r] = np.inf
    out[rows, cols] = dist
    return out


def stroke_values(distance, radius, soft=0.5):
    """a stroke's distances -> its mask 0..1: 1 to (1 - soft) of the radius, a smooth fall to 0 at the radius"""
    d = np.asarray(distance, np.float64)
    r = float(radius)
    core = r * (1.0 - float(soft))
    t = np.clip((d - core) / max(r - core, 1e-9), 0.0, 1.0)
    v = 1.0 - t * t * (3 - 2 * t)
    return np.where(np.isfinite(d), v, 0.0)
