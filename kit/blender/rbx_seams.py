"""DOES THE MAP MEET ITSELF ACROSS ITS SEAMS? (the owner's method lists, 2026-11-13: "texture seam checks"; the 3D
methods audit, stage G4.)

A UV seam is one edge of the mesh that lies in TWO places of the map (the surface was cut there to lay it flat).
The two places show the same line of the surface, so after the bake the colour must run on through the seam - when
it does not, the model shows a line there: a bake margin that did not reach, a texture laid on by its place in the
map and not in space, a pass baked at two sharpnesses.

Here: the seams found from the mesh (pure numpy), the baked map read at FOUR points across each seam - two inside
each island - and the colour's own run taken out. No Blender.

What was learnt building it (2026-11-15):
1. A step across a seam on a SHARP edge is not a fault - the two faces are shaded differently by the bake, and the
   crease hides the line: only seams on a smooth run of surface are judged (the caller says which: `smooth`, and
   the mesh's own shading).
2. One texel against one texel is noise - the texels of the two islands do not line up: readings are averaged over
   WINDOWS of a few texels along the edge.
3. Colour on one side against colour on the other measures the TEXTURE, not the seam (the review's null test: on
   built models the same share of "steps" came back comparing one side with itself a texel and a half deeper). So
   the surface's own run is taken out: with A2, A1 inside one island and B1, B2 inside the other, evenly spaced
   through the seam, a surface that runs on has B1 - A1 = the mean of its two slopes (A1 - A2) and (B2 - B1). What
   is left over is the seam's own step.
4. Even so a busy texture leaves something over. So the SAME reading is taken with no seam in it - four points
   wholly inside one island, beside the edge - and counted the same way: the map's FLOOR. What is judged is the
   seams' share beyond that floor.
5. (card 7cka, 2026-11-17) Readings are grouped in windows along each SEAM LINE (its edges chained end to end), not
   edge by edge: a dense mesh's seam is many edges under a texel or two each - judged one by one (under EDGE_MIN_PX
   each was skipped) a sculpted ball whose seams jump 71 levels was judged on none of its 1,228 seam edges. Only a
   whole seam line shorter than EDGE_MIN_PX goes unjudged now. A cut-out texel (alpha under half) on either side
   is not read; the normal and roughness maps are read too (a normal by its WORLD direction: each side's tangent
   frame turns it, the map's raw colours differ across every seam that rotates an island)."""

import numpy as np

INSET = 0.75          # texels inside the island of the first reading; the second is 2 x INSET deeper
WINDOW = 16.0         # texels of edge one judgement is averaged over
SAMPLES_MAX = 512     # readings along one edge, at most
SEEN = 12.0 / 255.0   # a step of colour this large across a line is seen (sRGB, the largest channel)
SEEN_ROUGH = 20.0 / 255.0   # ... of roughness (it shows as a change of the highlight: less sharp to the eye)
SEEN_NORMAL = 0.10    # ... of the surface's direction (radians, ~6 degrees: the light turns across the line)
# of the judged seams' length that may show a step before the build warns (the numbers measured on built models
# are on the skill page, beside what they do and do not show)
SHARE_BAR = 0.05
SMOOTH_DEG = 30.0     # the two faces of a seam turn no more than this: the surface runs on, a step there is seen
EDGE_MIN_PX = 3.0     # an edge shorter than this in the map is too short to average: not judged


def seam_edges(tv, uv_tri, eps=1e-5):
    """tv: (T, 3) vertex ids of the triangles; uv_tri: (T, 3, 2) their corners in the map.
    -> {"a": (S, 3, 2), "b": (S, 3, 2), "verts": (S, 2), "tris": (S, 2), "crowded": n} - every mesh edge two
    triangles share whose two ends do NOT lie on the same place of the map on both sides. a / b: [the edge's first
    end, its second end, the triangle's third corner] in the map, for each side, the ends in the same order; tris:
    the two triangles; crowded: edges three or more triangles share (never judged)."""
    tv, uv_tri = np.asarray(tv, np.int64), np.asarray(uv_tri, float)
    t = len(tv)
    k = np.arange(3)
    v0, v1 = tv[:, k].ravel(), tv[:, (k + 1) % 3].ravel()
    u0, u1, u2 = (uv_tri[:, (k + s) % 3].reshape(-1, 2) for s in range(3))
    swap = v0 > v1                                                        # every edge from its lower id to its higher
    lo, hi = np.where(swap, v1, v0), np.where(swap, v0, v1)
    ulo, uhi = np.where(swap[:, None], u1, u0), np.where(swap[:, None], u0, u1)
    key = lo * (int(tv.max()) + 1 if t else 1) + hi
    order = np.argsort(key, kind="stable")
    key = key[order]
    start = np.flatnonzero(np.r_[True, key[1:] != key[:-1]])
    count = np.diff(np.r_[start, len(key)])
    first = start[count == 2]                                             # (an edge of exactly two triangles)
    i, j = order[first], order[first + 1]
    apart = (np.abs(ulo[i] - ulo[j]).max(axis=1) > eps) | (np.abs(uhi[i] - uhi[j]).max(axis=1) > eps)
    i, j = i[apart], j[apart]
    return {"a": np.stack([ulo[i], uhi[i], u2[i]], axis=1), "b": np.stack([ulo[j], uhi[j], u2[j]], axis=1),
            "verts": np.stack([lo[i], hi[i]], axis=1), "tris": np.stack([i // 3, j // 3], axis=1),
            "crowded": int((count > 2).sum())}


def smooth(seams, pts, deg=SMOOTH_DEG, slack=0.5):
    """which seams lie on a SMOOTH run of surface: their two triangles turn no more than `deg` (and half a degree:
    a 12-sided cylinder turns exactly 30) from each other. pts: (T, 3, 3) the triangles' corners in space.
    -> (S,) bool"""
    pts = np.asarray(pts, float)
    n = np.cross(pts[:, 1] - pts[:, 0], pts[:, 2] - pts[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-20)
    t = seams["tris"]
    if len(t) == 0:
        return np.zeros(0, bool)
    return (n[t[:, 0]] * n[t[:, 1]]).sum(axis=1) >= np.cos(np.radians(deg + slack))


def read(img, uv):
    """the map read at points of it, between its texels (bilinear). img: (H, W, C), row 0 at v = 0; uv: (N, 2)."""
    img = np.asarray(img, float)
    h, w = img.shape[:2]
    x = np.clip(np.asarray(uv, float)[:, 0] * w - 0.5, 0, w - 1)
    y = np.clip(np.asarray(uv, float)[:, 1] * h - 0.5, 0, h - 1)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    x1, y1 = np.minimum(x0 + 1, w - 1), np.minimum(y0 + 1, h - 1)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    return (img[y0, x0] * (1 - fx) * (1 - fy) + img[y0, x1] * fx * (1 - fy)
            + img[y1, x0] * (1 - fx) * fy + img[y1, x1] * fx * fy)


def _inside(side, wh):
    """for each edge of one side: ONE TEXEL's step from the edge toward its triangle's third corner, in the map's
    own units (wh = the map's width and height in texels)"""
    a, b, c = side[:, 0] * wh, side[:, 1] * wh, side[:, 2] * wh           # in texels
    along = b - a
    n = np.stack([-along[:, 1], along[:, 0]], axis=1)
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    n *= np.where(((c - a) * n).sum(axis=1, keepdims=True) < 0, -1.0, 1.0)
    return n / wh


def chains(verts):
    """the seam edges joined end to end into LINES -> (line id per edge, the edge's start along its line, whether it
    runs reversed): a vertex two seam edges share continues a line; any other ends it. verts: (S, 2)"""
    verts = np.asarray(verts, np.int64)
    s_ = len(verts)
    line = np.full(s_, -1, np.int64)
    order = []
    if not s_:
        return line, order
    by_v = {}
    for e, (a, b) in enumerate(verts.tolist()):
        by_v.setdefault(a, []).append(e)
        by_v.setdefault(b, []).append(e)
    nid = 0
    for e0 in range(s_):
        if line[e0] >= 0:
            continue
        # walk back to the line's start, then forward along it
        e, at = e0, verts[e0][0]
        seen_ = {e0}
        while True:
            nxt = [f for f in by_v.get(int(at), []) if f != e and len(by_v[int(at)]) == 2 and line[f] < 0]
            if not nxt or nxt[0] in seen_:
                break
            e = nxt[0]
            seen_.add(e)
            at = verts[e][0] if verts[e][1] == at else verts[e][1]
        start_e, start_v = e, at
        seq = []
        e, v = start_e, start_v
        while e is not None and line[e] < 0:
            line[e] = nid
            rev = verts[e][1] == v          # (walked from its second end to its first)
            seq.append((e, bool(rev)))
            v = verts[e][0] if rev else verts[e][1]
            cand = [f for f in by_v.get(int(v), []) if f != e and line[f] < 0] if len(by_v.get(int(v), [])) == 2 else []
            e = cand[0] if cand else None
        order.append(seq)
        nid += 1
    return line, order


def measure(img, seams, keep=None, inset=INSET, seen=SEEN, window=WINDOW, alpha=None, to_world=None):
    """every judged seam read across itself, window by window along its seam LINE, the colour's own run taken out.
    img: (H, W, C) 0..1 (the first three channels are compared). keep: (S,) bool - the seams to judge, all when
    None. alpha: (H, W) 0..1 - a reading where either side is cut out (under half) is left out. to_world(values,
    side, edge, t) -> the readings turned into what is compared (a normal map: each side's tangent frame), side "a" /
    "b", edge the seam edge of each reading, t its place along that edge (0..1, from its first end). -> {"edges": judged, "length_px": their length in texels, "of_px": the
    length of ALL the seams (what was not judged: sharp, or on a line too short), "seen_px": the judged length whose
    windows show a step that is seen, "share",
    "floor": the share the same reading shows with NO seam in it (inside one island), "beyond": share - floor,
    "p95": the 95th percentile of the step by length, "worst": [(vertex a, vertex b, step)]}"""
    a, b, verts = seams["a"], seams["b"], seams["verts"]
    none = {"edges": 0, "length_px": 0.0, "of_px": 0.0, "seen_px": 0.0, "share": 0.0, "floor": 0.0, "beyond": 0.0,
            "p95": 0.0, "worst": []}
    if len(a) == 0:
        return none
    img = np.asarray(img, float)[..., :3]
    wh = np.array([img.shape[1], img.shape[0]], float)
    la = np.linalg.norm((a[:, 1] - a[:, 0]) * wh, axis=1)
    lb = np.linalg.norm((b[:, 1] - b[:, 0]) * wh, axis=1)
    of_px = float(np.maximum(la, lb).sum())
    use = np.ones(len(a), bool) if keep is None else np.asarray(keep, bool).copy()
    a, b, verts, length = a[use], b[use], verts[use], np.maximum(la, lb)[use]
    edge_ids = np.nonzero(use)[0]
    # the seam LINES: their edges end to end; a line shorter than EDGE_MIN_PX is not judged
    line, order_ = chains(verts)
    pos0 = np.zeros(len(a))                                               # each edge's start along its line (texels)
    line_len = np.zeros(len(order_))
    for k_, seq in enumerate(order_):
        run = 0.0
        for e_, _rev in seq:
            pos0[e_] = run
            run += length[e_]
        line_len[k_] = run
    ok = line_len[line] >= EDGE_MIN_PX if len(a) else np.zeros(0, bool)
    a, b, verts, length, pos0, line, edge_ids = a[ok], b[ok], verts[ok], length[ok], pos0[ok], line[ok], edge_ids[ok]
    if len(a) == 0:
        return {**none, "of_px": round(of_px, 1)}
    n = np.clip(np.ceil(length).astype(int), 1, SAMPLES_MAX)
    edge = np.repeat(np.arange(len(a)), n)
    j = np.concatenate([np.arange(k) for k in n])
    t = ((j + 0.5) / n[edge])[:, None]
    ia, ib = _inside(a, wh)[edge], _inside(b, wh)[edge]
    la_, lb_ = a[edge, 0] + t * (a[edge, 1] - a[edge, 0]), b[edge, 0] + t * (b[edge, 1] - b[edge, 0])

    def rd(at, side):
        v = read(img, at)
        return to_world(v, side, edge_ids[edge], t[:, 0]) if to_world is not None else v
    a1, a2 = rd(la_ + ia * inset, "a"), rd(la_ + ia * inset * 3, "a")
    b1, b2 = rd(lb_ + ib * inset, "b"), rd(lb_ + ib * inset * 3, "b")
    # the seam's own step: what B1 - A1 holds beyond the surface's run (the mean of the two slopes)
    left = (b1 - a1) - 0.5 * ((a1 - a2) + (b2 - b1))
    # the floor: the same reading through four points of island A alone (no seam between them)
    a3, a4 = rd(la_ + ia * inset * 5, "a"), rd(la_ + ia * inset * 7, "a")
    still = (a2 - a3) - 0.5 * ((a3 - a4) + (a1 - a2))
    # a reading counts only INSIDE its own triangle: a strip of an island a few texels wide (a turned lip laid as
    # narrow rings) put the deeper readings on the NEXT strip - another ring's colour, a 160-level "step" that was
    # not a seam (card 7cka; his limitations review: "handling <3-texel thin islands"). Each side's room: its
    # triangle's height over the seam edge, in texels
    def room(side):
        e_ = (side[:, 1] - side[:, 0]) * wh
        c_ = (side[:, 2] - side[:, 0]) * wh
        return np.abs(e_[:, 0] * c_[:, 1] - e_[:, 1] * c_[:, 0]) / np.maximum(np.linalg.norm(e_, axis=1), 1e-12)
    ra, rb = room(a)[edge], room(b)[edge]
    wt = ((ra > inset * 3) & (rb > inset * 3)).astype(float)               # (A2 and B2 inside)
    wt0 = (ra > inset * 7).astype(float)                                    # (the floor's A4 inside)
    if alpha is not None:   # (a cut-out texel on either side: not read)
        al = np.asarray(alpha, float)[..., None]
        wt = wt * ((read(al, la_ + ia * inset)[:, 0] >= 0.5) & (read(al, lb_ + ib * inset)[:, 0] >= 0.5)).astype(float)
    # windows ALONG EACH LINE: a reading's place on its line, WINDOW texels a window
    at_line = pos0[edge] + t[:, 0] * length[edge]
    n_lines = int(line.max()) + 1
    wins_line = np.zeros(n_lines, np.int64)
    np.maximum.at(wins_line, line, np.floor((pos0 + length) / window).astype(np.int64) + 1)
    first = np.r_[0, np.cumsum(wins_line)[:-1]]
    gid = first[line[edge]] + np.minimum(np.floor(at_line / window).astype(np.int64), wins_line[line[edge]] - 1)
    total_w = int(wins_line.sum())
    dims = left.shape[1]
    acc, acc0, cnt, cnt0 = np.zeros((total_w, dims)), np.zeros((total_w, dims)), np.zeros(total_w), np.zeros(total_w)
    np.add.at(acc, gid, left * wt[:, None])
    np.add.at(acc0, gid, still * wt0[:, None])
    np.add.at(cnt, gid, wt)
    np.add.at(cnt0, gid, wt0)
    vec = to_world is not None
    meanv, mean0 = acc / np.maximum(cnt, 1)[:, None], acc0 / np.maximum(cnt0, 1)[:, None]
    step = np.linalg.norm(meanv, axis=1) if vec else np.abs(meanv).max(axis=1)     # per window
    step0 = np.linalg.norm(mean0, axis=1) if vec else np.abs(mean0).max(axis=1)
    step0 = np.where(cnt0 > 0, step0, 0.0)
    w_px = np.zeros(total_w)                                              # the texels each window holds
    np.add.at(w_px, gid, (length[edge] / n[edge]) * wt)
    live = cnt > 0
    has0 = (cnt0 > 0)[live]   # (the windows a floor could be read in: an island deep enough beside the seam)
    step, step0, w_len = step[live], step0[live], w_px[live]
    if not len(step):
        return {**none, "of_px": round(of_px, 1)}
    seen_px = float(w_len[step > seen].sum())
    total = float(w_len.sum())
    # the floor's share over the windows that HAVE one (a thin island reads no floor: counted as none, a floor read
    # in few windows came out low and every busy texture "stepped")
    tot0 = float(w_len[has0].sum())
    floor = float(w_len[has0 & (step0 > seen)].sum()) / tot0 if tot0 else 0.0
    order = np.argsort(step)
    cum = np.cumsum(w_len[order])
    p95 = float(step[order][min(len(step) - 1, int(np.searchsorted(cum, 0.95 * cum[-1])))])
    worst_of = np.zeros(len(a))
    st_all = np.zeros(total_w)
    st_all[live] = step
    np.maximum.at(worst_of, edge, st_all[gid])
    top = np.argsort(-worst_of)[:5]
    return {"edges": int(len(a)), "length_px": round(total, 1), "of_px": round(of_px, 1),
            "seen_px": round(seen_px, 1), "share": round(seen_px / total, 4) if total else 0.0,
            "floor": round(floor, 4), "beyond": round(max(0.0, seen_px / total - floor), 4) if total else 0.0,
            "p95": round(p95, 4),
            "worst": [(int(verts[k, 0]), int(verts[k, 1]), round(float(worst_of[k]), 4)) for k in top
                      if worst_of[k] > seen]}
