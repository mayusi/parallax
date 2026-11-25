"""EDGE FLOW, MOVED (the owner's method lists: "edge flow"; the 3D methods audit's PARTLY: "a tool that moves vertices
or slides a loop to redistribute flow is not built"). Blender's LoopTools Relax / Space, done by the kit: every
vertex of a part slides over the part's OWN surface toward the middle of its neighbours, so loops bunched together
spread out evenly and needle triangles open up - and the shape is held: a vertex on a sharp edge or on the part's
border slides ALONG that edge only (it is laid back on the edge's own line), a corner (where three or more such
edges meet, or one ends) never moves, and every free vertex is laid back on the surface it started on.

`classify` sorts the vertices, `relax` moves them, `spread` measures the flow before and after (how much the
lengths of the edges vary: their coefficient of variation), `on_segments` lays a point back on a polyline.
Pure numpy; the surface is a callable (rbx: the part's own mesh, through a BVH)."""

import numpy as np

SHARP_DEG = 30.0   # an edge whose two faces turn more than this is a sharp edge: vertices slide along it, never off
STRENGTH = 0.5     # each pass moves a vertex this share of the way to its neighbours' middle
ITERATIONS = 20
CORNER_DEG = 1.0   # two held edges meeting at a vertex that turn more than this make it a corner: a vertex slides only where its sharp edge runs STRAIGHT (a 16-sided rim turning 22.5 deg a vertex slid round its own outline and moved the rod 0.25 mm)
IN_LINE = 0.9      # two edges at a vertex this near to one line (|cos|) are one run of a loop (spread compares them)


def classify(points, edges, held, corner_deg=CORNER_DEG):
    """which vertex may move how: edges (E, 2); held (E,) bool - a sharp or border edge
    -> (kind (V,): 0 free, 1 on a chain of held edges (exactly two meet there, near one line), 2 a corner (one, three
    or more meet, or two turning past corner_deg); chain neighbours [the two vertices along its chain, or []])"""
    p = np.asarray(points, float).reshape(-1, 3)
    e = np.asarray(edges, int).reshape(-1, 2)
    h = np.asarray(held, bool)
    along = [[] for _ in range(len(p))]
    for a_, b_ in e[h]:
        along[a_].append(int(b_))
        along[b_].append(int(a_))
    kind = np.zeros(len(p), int)
    cos_max = np.cos(np.radians(corner_deg))
    for v, nb in enumerate(along):
        if not nb:
            continue
        if len(nb) != 2:
            kind[v] = 2
            continue
        d1, d2 = p[v] - p[nb[0]], p[nb[1]] - p[v]
        c = float(np.dot(d1, d2) / max(np.linalg.norm(d1) * np.linalg.norm(d2), 1e-30))
        kind[v] = 1 if c >= cos_max else 2
    return kind, [along[v] if kind[v] == 1 else [] for v in range(len(p))]


def on_segments(points, a, b):
    """each point laid on the nearest of the segments a[i]-b[i] -> (N, 3)"""
    p = np.asarray(points, float).reshape(-1, 3)
    a, b = np.asarray(a, float).reshape(-1, 3), np.asarray(b, float).reshape(-1, 3)
    if not len(a):
        return p.copy()
    d = b - a
    ll = np.maximum((d * d).sum(1), 1e-30)
    out = np.empty_like(p)
    step = max(1, 2_000_000 // max(len(a), 1))   # (in chunks: a 3000-edge border is 216 MB a pass in one piece)
    for i in range(0, len(p), step):
        pc = p[i:i + step]
        t = np.clip(((pc[:, None, :] - a[None]) * d[None]).sum(2) / ll[None], 0.0, 1.0)
        q = a[None] + t[..., None] * d[None]
        best = ((q - pc[:, None, :]) ** 2).sum(2).argmin(1)
        out[i:i + step] = q[np.arange(len(pc)), best]
    return out


def relax(points, edges, kind, chain, project, iterations=ITERATIONS, strength=STRENGTH, held_edges=None):
    """the vertices slid toward their neighbours' middle, `iterations` passes of `strength`: free ones laid back on
    the surface by project((N, 3) points, (N,) their vertex indices) -> (N, 3) (rbx: each on its OWN smooth region,
    never across a sharp edge onto the next); a vertex with no edge never moves; chain ones on their own held edges' ORIGINAL lines (held_edges: the
    (E, 2) held edges, whose first places the chains keep); corners never -> (N, 3)"""
    p0 = np.asarray(points, float).reshape(-1, 3)
    p = p0.copy()
    e = np.asarray(edges, int).reshape(-1, 2)
    kind = np.asarray(kind)
    free = None   # (after the degrees: a vertex with no edge has no neighbours' middle - it stays)
    on = np.flatnonzero(kind == 1)
    a_, b_ = np.concatenate([e[:, 0], e[:, 1]]), np.concatenate([e[:, 1], e[:, 0]])
    deg = np.zeros(len(p))
    np.add.at(deg, a_, 1.0)
    free = np.flatnonzero((kind == 0) & (deg > 0))
    he = np.asarray(held_edges, int).reshape(-1, 2) if held_edges is not None else np.zeros((0, 2), int)
    cn = np.array([chain[v] for v in on], int).reshape(-1, 2)
    # (each chain vertex is laid back on ITS OWN chain only - the run of held edges it lies on, from corner to
    # corner: never on the border round the corner from it)
    runs = _runs(len(p0), he, kind)
    mine = {}
    for v in on:
        mine.setdefault(runs.get(int(v), -1), []).append(int(v))
    er = np.array(_edge_runs(he, runs), int) if len(he) else np.zeros(0, int)   # (once: grouped by run below)
    segs = {r: (p0[he[er == r][:, 0]], p0[he[er == r][:, 1]]) for r in mine}
    where = {int(v): i for i, v in enumerate(on)}
    for _ in range(int(iterations)):
        mid = np.zeros_like(p)
        np.add.at(mid, a_, p[b_])
        mid /= np.maximum(deg, 1.0)[:, None]
        nxt = p.copy()
        if len(free):
            nxt[free] = project(p[free] + strength * (mid[free] - p[free]), free)
        if len(on):
            cm = (p[cn[:, 0]] + p[cn[:, 1]]) / 2.0
            want = p[on] + strength * (cm - p[on])
            for r, vs in mine.items():
                idx = [where[v] for v in vs]
                nxt[vs] = on_segments(want[idx], *segs[r])
        p = nxt
    return p


def _runs(n_verts, held_edges, kind):
    """the chains: held edges joined through chain vertices (never through a corner) -> {chain vertex: run id}"""
    parent = list(range(len(held_edges)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    at = {}
    for k, (a_, b_) in enumerate(np.asarray(held_edges, int).reshape(-1, 2)):
        for v in (int(a_), int(b_)):
            if kind[v] == 1:
                if v in at:
                    parent[root(k)] = root(at[v])
                else:
                    at[v] = k
    return {v: root(k) for v, k in at.items()}


def _edge_runs(held_edges, runs):
    """each held edge's run id (by either end that is a chain vertex; -1: corner to corner)"""
    out = []
    for a_, b_ in np.asarray(held_edges, int).reshape(-1, 2):
        out.append(runs.get(int(a_), runs.get(int(b_), -1)))
    return out


def spread(points, edges, in_line=IN_LINE):
    """how evenly the loops are laid: along every run of a loop (two edges at a vertex near one line), how much one
    edge's length differs from the next - the mean |ln(a / b)| (0 = loops evenly spaced; bunched loops: large).
    A sheet of long rectangles laid evenly is 0: it compares each edge with the one IN LINE with it -> float"""
    p = np.asarray(points, float).reshape(-1, 3)
    e = np.asarray(edges, int).reshape(-1, 2)
    if not len(e):
        return 0.0
    at = [[] for _ in range(len(p))]
    look = range(len(p)) if len(p) <= 20000 else np.random.default_rng(7).choice(len(p), 20000, replace=False)
    for k, (a_, b_) in enumerate(e):
        at[a_].append((k, b_))
        at[b_].append((k, a_))
    ln = np.maximum(np.linalg.norm(p[e[:, 0]] - p[e[:, 1]], axis=1), 1e-30)
    out = []
    for v in look:
        es = at[v]
        for i_ in range(len(es)):
            for j_ in range(i_ + 1, len(es)):
                d1, d2 = p[es[i_][1]] - p[v], p[es[j_][1]] - p[v]
                c = float(np.dot(d1, d2) / max(np.linalg.norm(d1) * np.linalg.norm(d2), 1e-30))
                if c <= -in_line:
                    out.append(abs(np.log(ln[es[i_][0]] / ln[es[j_][0]])))
    return float(np.mean(out)) if out else 0.0
