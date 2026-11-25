"""rbx_regions.py — a generated shape's COLOUR REGIONS -> kit materials (import_mesh(regions=), kit make). Plain numpy,
no Blender: unit-tested (kit/test/python/test_regions.py).

The owner rated the first made props 2 / 0 / 3.5 — "the colour and texture are horrible, the model is good" (2026-10-16):
the generator's own texture is muddy (its lighting baked in, streaks, blur). Its FORM is kept; its colours only say
which part is what — a red body, a black hose, a steel valve — and each part takes a real kit finish.

  clusters(rgb, weight, k_max)        the texture's colours (per face, area-weighted) -> a few clusters
  choose(cluster, share, words)       a cluster -> a kit material recipe (finish / scan / colour)
  nearest(rgb, targets)               each face -> its cluster
  smooth(labels, edges, passes)       a majority vote over each face's neighbours (no speckle at shading changes)
"""
import numpy as np


def srgb_to_linear(c):
    c = np.clip(np.asarray(c, np.float64) / 255.0, 0.0, 1.0)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _dist(a, b):
    """'redmean' colour distance on sRGB 0-255 (cheap, closer to the eye than plain RGB): (n,3) x (k,3) -> (n,k)"""
    a = np.asarray(a, np.float64)[:, None, :]
    b = np.asarray(b, np.float64)[None, :, :]
    rm = (a[..., 0] + b[..., 0]) / 2.0
    d = a - b
    return np.sqrt((2 + rm / 256) * d[..., 0] ** 2 + 4 * d[..., 1] ** 2 + (2 + (255 - rm) / 256) * d[..., 2] ** 2)


def nearest(rgb, targets):
    return np.argmin(_dist(rgb, targets), axis=1)


def family(srgb):
    """a colour's FAMILY — what kind of surface it says, not its shade: a hue (chromatic colours; a shadowed red is
    still red) or a grey level (dark / mid / light: black rubber, steel, a white pane differ)"""
    r, g, b = (float(v) for v in srgb)
    hi, lo = max(r, g, b), min(r, g, b)
    chroma, lum = hi - lo, 0.2126 * r + 0.7152 * g + 0.0722 * b
    if chroma < 28 or (hi > 0 and chroma / hi < 0.22):
        return ("grey", 0 if lum < 60 else 2 if lum > 200 else 1)
    if hi == r:
        hue = (60 * ((g - b) / chroma)) % 360
    elif hi == g:
        hue = 60 * ((b - r) / chroma) + 120
    else:
        hue = 60 * ((r - g) / chroma) + 240
    return ("hue", hue)


def same_family(a, b, hue_tol=28.0):
    fa, fb = family(a), family(b)
    if fa[0] != fb[0]:
        return False
    if fa[0] == "grey":
        return fa[1] == fb[1]
    d = abs(fa[1] - fb[1]) % 360
    return min(d, 360 - d) <= hue_tol


def _kmeans(rgb, w, k, rng):
    cent = [rgb[rng.choice(len(rgb), p=w)]]   # (k-means++ seeding, weighted)
    for _ in range(1, k):
        d = np.min(_dist(rgb, np.array(cent)), axis=1) ** 2 * w
        cent.append(rgb[rng.choice(len(rgb), p=d / max(d.sum(), 1e-12))] if d.sum() > 0 else rgb[0])
    cent = np.array(cent)
    for _ in range(30):
        lab = nearest(rgb, cent)
        new = np.array([np.average(rgb[lab == j], axis=0, weights=w[lab == j]) if (lab == j).any() else cent[j]
                        for j in range(k)])
        if np.allclose(new, cent, atol=0.5):
            break
        cent = new
    return cent


def clusters(rgb, weight=None, k_max=6, min_share=0.015, seed=0):
    """the surfaces the texture's colours say: weighted k-means (k_max) over the faces' colours, then clusters of the
    same FAMILY merged (a shadowed red is the red paint — measured: the made extinguisher's (82, 38, 37) was its
    shading — while a small grey valve beside it stays: 3% of the area), a family under min_share given to its
    nearest -> [(srgb, share)], the biggest first; each family's colour is its most-covered member's"""
    rgb = np.asarray(rgb, np.float64)
    w = np.ones(len(rgb)) if weight is None else np.asarray(weight, np.float64)
    w = w / max(w.sum(), 1e-12)
    cent = _kmeans(rgb, w, min(k_max, len(rgb)), np.random.default_rng(seed))
    lab = nearest(rgb, cent)
    shares = np.array([w[lab == j].sum() for j in range(len(cent))])
    groups = []   # [[member indices]]
    for j in np.argsort(-shares):
        for gr in groups:
            if same_family(cent[gr[0]], cent[j]):
                gr.append(j)
                break
        else:
            groups.append([j])
    fam = [(cent[gr[0]], float(shares[gr].sum()), [cent[j] for j in gr]) for gr in groups]
    keep = [f for f in fam if f[1] >= min_share] or [max(fam, key=lambda f: f[1])]
    dropped = [f for f in fam if f[1] < min_share]
    if dropped and keep:   # (a stray family's area — and its shades — to the biggest)
        keep[0] = (keep[0][0], keep[0][1] + sum(f[1] for f in dropped), keep[0][2] + [c for f in dropped for c in f[2]])
    keep.sort(key=lambda f: -f[1])
    rnd = lambda c: tuple(float(round(v, 1)) for v in c)  # noqa: E731
    return [(rnd(c), float(round(s, 4)), [rnd(m) for m in members]) for c, s, members in keep]


def nearest_family(rgb, families):
    """each face -> its family index, matched against EVERY shade the family merged (its dark and light wood alike):
    matched against one colour per family, the made barrel's shaded wood went to the steel — 36% for a 12% region"""
    cols, idx = [], []
    for i, members in enumerate(families):
        members = members if isinstance(members[0], (list, tuple)) else [members]
        for m in members:
            cols.append(m)
            idx.append(i)
    return np.asarray(idx)[nearest(rgb, np.asarray(cols, np.float64))]


# the kit's wood scans (ambientCG, CC0) and their colour maps' mean sRGB, measured 2026-10-16 at 256 px
WOOD_SCANS = {"Wood049": (123, 99, 77), "Wood051": (65, 52, 46), "Wood066": (89, 51, 19), "Wood092": (175, 114, 63),
              "Wood096": (179, 157, 132)}
WOOD_WORDS = ("wood", "wooden", "barrel", "crate", "chest", "keg", "cask", "plank", "log", "oak", "pine", "table", "chair")


def choose(srgb, share, words):
    """a colour cluster -> {name, finish | scan, color (linear), why}: the finish a part of that colour most likely is.
    Saturated -> painted metal in that colour; near black -> rubber when a small part (a hose, a grip), black-painted
    metal when it is the body (cast iron); grey -> machined steel (chrome when bright); yellowish metal -> polished
    brass; brown -> wood with its scan when the words say wood; near white -> a pale polymer (a lamp's pane)"""
    r, g, b = (float(v) for v in srgb)
    hi, lo = max(r, g, b), min(r, g, b)
    chroma, lum = hi - lo, 0.2126 * r + 0.7152 * g + 0.0722 * b
    text = " ".join(words).lower()
    lin = tuple(float(round(v, 4)) for v in srgb_to_linear((r, g, b)))
    woody = any(w in text for w in WOOD_WORDS)
    if woody and r >= g >= b and chroma >= 18 and lum >= 40:
        # the kit's wood scan NEAREST its measured colour (the scan's colour is the surface: scan_mix=1): always the
        # palest one, Wood096, made the barrel's (141, 116, 82) oak a plain beige
        scan = min(WOOD_SCANS, key=lambda k: float(_dist(np.array([[r, g, b]], float),
                                                         np.array([WOOD_SCANS[k]], float))[0, 0]))
        return {"kind": "wood", "color": lin, "scan": scan, "why": f"brown and the words say wood: {scan}, the "
                                                                  "nearest wood scan"}
    if lum < 50 and chroma < 40:
        if share < 0.3:
            return {"kind": "rubber", "finish": "rubber", "color": None, "why": "near black, a small part (a hose, a grip)"}
        return {"kind": "black_paint", "finish": "painted_metal", "color": lin, "why": "near black, the body (painted metal)"}
    if chroma >= 55:
        if r > b and g > b and abs(r - g) < 60 and lum > 90 and b < 0.6 * g:
            return {"kind": "brass", "finish": "polished_brass", "color": None, "why": "yellowish metal"}
        return {"kind": "paint", "finish": "painted_metal", "color": lin, "why": "a saturated colour: paint"}
    if lum > 215:
        return {"kind": "pale", "finish": "polymer", "color": lin, "why": "near white (a pane, a label)"}
    if chroma < 30:
        # (its MEASURED grey, as paint keeps its colour: machined steel's own is near white — the made barrel's iron
        #  hoops, (125, 122, 115) in its texture, rendered as white smears on the wood)
        if lum > 190:
            return {"kind": "steel", "finish": "chrome", "color": None, "why": "bright grey: polished metal"}
        return {"kind": "steel", "finish": "machined_steel", "color": lin, "why": "grey: bare metal, its measured tone"}
    return {"kind": "paint", "finish": "painted_metal", "color": lin, "why": "a muted colour: paint"}


def despeckle(labels, edges, area, min_share=0.004):
    """connected patches of one region smaller than min_share of the whole area -> the region around them (the made
    barrel's worn light spots read as scattered steel splotches over the wood; its hoops are long connected rings and
    stay). labels (n,), edges (m,2) face pairs, area (n,) -> labels"""
    lab = np.asarray(labels).copy()
    e = np.asarray(edges, np.int64).reshape(-1, 2)
    n = len(lab)
    if not len(e) or n == 0:
        return lab
    area = np.asarray(area, np.float64)
    total = max(area.sum(), 1e-12)
    same = e[lab[e[:, 0]] == lab[e[:, 1]]]
    parent = np.arange(n)

    def find(x):
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    for a, b in same:   # (union-find over same-region neighbours: the patches)
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    comp = np.array([find(i) for i in range(n)])
    comp_area = np.bincount(comp, weights=area, minlength=n)
    small = comp_area[comp] < min_share * total
    if not small.any():
        return lab
    k = int(lab.max()) + 1
    border = e[comp[e[:, 0]] != comp[e[:, 1]]]
    votes = {}
    for a, b in border:   # (each small patch: the region of what borders it, weighted by the bordering faces' area)
        for x, y in ((a, b), (b, a)):
            if small[x] and not small[y]:
                v = votes.setdefault(comp[x], np.zeros(k))
                v[lab[y]] += area[y]
    for c, v in votes.items():
        lab[comp == c] = int(np.argmax(v))
    return lab


def smooth(labels, edges, passes=2):
    """labels (n,), edges (m,2) face-adjacency pairs -> labels where each face takes its neighbours' majority when
    most of them disagree with it (shading changes in the texture leave speckle)"""
    lab = np.asarray(labels).copy()
    e = np.asarray(edges, np.int64).reshape(-1, 2)
    if not len(e):
        return lab
    k = int(lab.max()) + 1
    for _ in range(passes):
        votes = np.zeros((len(lab), k))
        np.add.at(votes, (e[:, 0], lab[e[:, 1]]), 1)
        np.add.at(votes, (e[:, 1], lab[e[:, 0]]), 1)
        total = votes.sum(1)
        top = votes.argmax(1)
        idx = np.arange(len(lab))
        # (2+ neighbours, a clear majority against it: a face with one neighbour never flips — the speck and its
        #  neighbours traded labels back and forth)
        flip = (total >= 2) & (top != lab) & (votes[idx, top] > 0.5 * total) & (votes[idx, top] > votes[idx, lab])
        lab[flip] = top[flip]
    return lab
