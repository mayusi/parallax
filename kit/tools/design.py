"""design.py — `kit design`: CREATIVE DIRECTION for 3D pieces (the owner, 2026-10-25: "work on originality, making
original type weapons ... a creative director and creative direction in the pipeline"; the plan: "3D Creative
Direction & Originality Plan"). An original piece is DECIDED before it is built, the way a studio's art director
decides: a direction doc (kit/direction.py, lane 3d), the MAKER's design language it belongs to, a wide silhouette
exploration, the owner's pick, a concept sheet the 3D route builds from, and a director's review of the result.

    lune run kit design direction <Piece> [--new]      the direction doc: assets/models/direction/<Piece>.md
    lune run kit design maker <Maker> [--new]          a maker's design language: assets/models/makers/<Maker>.md
    lune run kit design explore <Piece> [--n 12] [--seed 1] [--fresh [--only A,B]] [--record <answers.json>] [--no-screen]
        a SILHOUETTE EXPLORATION per direction: n side-view concepts drawn (local FLUX.2, one load a direction), cut
        out, measured (proportion, solidity, outline complexity; readable at 32 px; ORIGINAL: SigLIP 2 + DINOv2
        distance to our past pieces), kept in a quality-diversity grid (the best design of each kind: strong options
        that differ), each direction's best saved as its Sheet; the pick board -> build/design/<Piece>/board.png.
        The doc's bans screen every candidate first (the local VLM; without one a packet for the AI client,
        build/design/<Piece>/bans_packet.json + bans_PROMPT.md, answered with --record - no Sheet until then;
        --no-screen goes on without the screen, on purpose)
    lune run kit design concept <Piece> --from <picked silhouette> [--what "<the object>"] [--n 4]
        the CONCEPT SHEET the 3D route builds from: the pick redrawn as a clean side view (kept only while its outline
        stays on the pick's), front and top drawn from that side (kept by how their size agrees), a three-quarter
        look -> <models>/direction/<Piece>.{side,front,top,three_quarter,concept}.png + .concept.json
    lune run kit design review <Piece> --asset <name> [--sheet <png>] [--part <word>] [--view left|side]
        the DIRECTOR's review of a finished build against its direction: the picked sheet's silhouette, readable at
        32 px, original (distance to our past pieces), the maker's detail share, every ban and pillar asked of the
        local vision model as a yes / no question -> one fix list, worst first

A MAKER doc (Destiny's weapon foundries are the model: every gun of one maker shares its language, two makers never
look alike) — `# <Maker> — design language`, then these sections:
  Identity      one sentence (<= 40 words): who makes these, for whom, and why they look the way they do
  Shape family  "- primary: <shape>" and "- secondary: <shape>" (round / square / triangle / blade / tube / organic)
  Motif         >= 1 bullet: the signature element every piece carries (a whiplash curve, a stepped crown ...)
  Edges         "- rule: round|chamfer|crisp|mixed" and "- radius_mm: <n>"
  Materials     2-4 bullets "<material> — <finish>"
  Detail        "- share: <10-50>" (% of the surface carrying detail: the rest is quiet, so the eye rests)
  Bans          >= 3 bullets: what this maker never does
Two makers in the folder must differ on >= 2 of: primary shape, edge rule, materials, motif.
"""

import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "kit"))
SHAPES = ("round", "square", "triangle", "blade", "tube", "organic")
EDGE_RULES = ("round", "chamfer", "crisp", "mixed")
MAKER_SECTIONS = ["Identity", "Shape family", "Motif", "Edges", "Materials", "Detail", "Bans"]

MAKER_TEMPLATE = """# {name} — design language

Every piece {name} makes carries this language; another maker's never does. Fill each section, then check it.

## Identity
TODO: one sentence: who makes these, for whom, and why they look the way they do.

## Shape family
- primary: TODO (round / square / triangle / blade / tube / organic)
- secondary: TODO

## Motif
- TODO: the signature element every piece carries

## Edges
- rule: TODO (round / chamfer / crisp / mixed)
- radius_mm: TODO

## Materials
- TODO <material> — <finish>
- TODO <material> — <finish>

## Detail
- share: TODO (10-50: % of the surface that carries detail)

## Bans
- TODO
- TODO
- TODO
"""


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def _sections(text):
    out, cur = {}, None
    for ln in text.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", ln)
        if m:
            cur = m.group(1).strip()
            out[cur] = []
        elif cur is not None:
            out[cur].append(ln.rstrip())
    return out


def _bullets(lines):
    return [ln[2:].strip() for ln in lines if ln.startswith("- ")]


def _kv(lines):
    out = {}
    for b in _bullets(lines):
        if ":" in b:
            k, v = b.split(":", 1)
            out[k.strip().lower()] = v.strip()
    return out


def parse_maker(path):
    """the maker doc as data: {name, identity, primary, secondary, motif[], edge_rule, radius_mm, materials[],
    detail_share, bans[]} (missing values None / empty) — what a build reads (a.maker) and the check compares"""
    text = open(path, encoding="utf-8").read()
    sec = _sections(text)
    m = re.match(r"^#\s+(.+?)\s+[—-]\s+design language", text.strip())
    shape, edges, detail = _kv(sec.get("Shape family", [])), _kv(sec.get("Edges", [])), _kv(sec.get("Detail", []))
    num = lambda s: float(re.findall(r"[\d.]+", s)[0]) if s and re.findall(r"[\d.]+", s) else None  # noqa: E731
    return {"name": m.group(1).strip() if m else os.path.splitext(os.path.basename(path))[0],
            "identity": " ".join(ln.strip() for ln in sec.get("Identity", []) if ln.strip()),
            "primary": shape.get("primary", "").split()[0].lower() if shape.get("primary") else None,
            "secondary": shape.get("secondary", "").split()[0].lower() if shape.get("secondary") else None,
            "motif": _bullets(sec.get("Motif", [])),
            "edge_rule": edges.get("rule", "").split()[0].lower() if edges.get("rule") else None,
            "radius_mm": num(edges.get("radius_mm")),
            "materials": _bullets(sec.get("Materials", [])),
            "detail_share": num(detail.get("share")),
            "bans": _bullets(sec.get("Bans", [])), "sections": list(sec)}


def _material_names(mk):
    return {re.split(r"\s+[—-]\s+", m)[0].strip().lower() for m in mk["materials"]}


def differences(a, b):
    """which of the four identity rules two makers differ on"""
    diff = []
    if a["primary"] != b["primary"]:
        diff.append("primary shape")
    if a["edge_rule"] != b["edge_rule"]:
        diff.append("edge rule")
    if _material_names(a) != _material_names(b):
        diff.append("materials")
    words = lambda mk: set(re.findall(r"[a-z]{4,}", " ".join(mk["motif"]).lower()))  # noqa: E731
    if not (words(a) & words(b)):
        diff.append("motif")
    return diff


def check_maker(path):
    """(status draft|ready, problems, maker)"""
    mk = parse_maker(path)
    text = open(path, encoding="utf-8").read()
    probs = [f'no "## {s}" section' for s in MAKER_SECTIONS if s not in mk["sections"]]
    if "TODO" in text:
        probs.append("TODO left in the doc")
    n = len(mk["identity"].split())
    if n == 0 or n > 40:
        probs.append(f"Identity is {n} words (one sentence, <= 40)")
    for k in ("primary", "secondary"):
        if mk[k] not in SHAPES:
            probs.append(f"Shape family {k}: {mk[k]!r} (one of {', '.join(SHAPES)})")
    if not mk["motif"]:
        probs.append("no Motif bullet")
    if mk["edge_rule"] not in EDGE_RULES:
        probs.append(f"Edges rule: {mk['edge_rule']!r} (one of {', '.join(EDGE_RULES)})")
    if mk["radius_mm"] is None:
        probs.append("Edges radius_mm missing")
    if not 2 <= len(mk["materials"]) <= 4 or any(not re.search(r"\s[—-]\s", m) for m in mk["materials"]):
        probs.append(f"{len(mk['materials'])} Materials (2-4, each '<material> — <finish>')")
    if mk["detail_share"] is None or not 10 <= mk["detail_share"] <= 50:
        probs.append(f"Detail share {mk['detail_share']} (10-50 %: the rest of the surface stays quiet)")
    if len(mk["bans"]) < 3:
        probs.append(f"{len(mk['bans'])} Bans (>= 3)")
    folder = os.path.dirname(os.path.abspath(path))
    for f in sorted(os.listdir(folder)):
        other = os.path.join(folder, f)
        if f.endswith(".md") and os.path.abspath(other) != os.path.abspath(path):
            om = parse_maker(other)
            d = differences(mk, om)
            if len(d) < 2:
                probs.append(f"too close to {om['name']}: differs only on {', '.join(d) or 'nothing'} (>= 2 of "
                             "primary shape, edge rule, materials, motif - two makers must never look alike)")
    return ("draft" if probs else "ready"), probs, mk


def _arg(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default


def build_root(argv=()):
    """the active game's build folder (as models_root), else the project's"""
    m = models_root(argv)
    g = os.path.dirname(os.path.dirname(m))
    return os.path.join(g, "build") if os.path.basename(os.path.dirname(g)) == "games" else os.path.join(REPO, "build")


def models_root(argv=()):
    """the active game's assets/models (--game <Name> > env KIT_GAME > games/.active, as kit/lib/config.luau),
    else the project root's"""
    game = _arg(list(argv), "--game") or os.environ.get("KIT_GAME")
    if not game:
        act = os.path.join(REPO, "games", ".active")
        game = open(act, encoding="utf-8").read().strip() if os.path.isfile(act) else None
    if game and game.lower() != "none" and os.path.isdir(os.path.join(REPO, "games", game)):
        return os.path.join(REPO, "games", game, "assets", "models")
    return os.path.join(REPO, "assets", "models")


def cmd_maker(argv):
    if not argv or argv[0].startswith("--"):
        return emit("fail", "design maker: which maker?", "lune run kit design maker <Maker> [--new]")
    name = argv[0]
    folder = _arg(argv, "--dir") or os.path.join(models_root(argv), "makers")
    path = os.path.join(folder, f"{name}.md")
    if "--new" in argv:
        if os.path.isfile(path):
            return emit("fail", f"{path} exists (never overwritten)", f"edit it, then: lune run kit design maker {name}")
        os.makedirs(folder, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(MAKER_TEMPLATE.format(name=name))
        return emit("pass", f"design maker: template written: {os.path.relpath(path, REPO)}",
                    "write the language (identity, shapes, motif, edges, materials, detail share, bans), then check it")
    if not os.path.isfile(path):
        return emit("fail", f"design maker: no {os.path.relpath(path, REPO)}", f"lune run kit design maker {name} --new")
    status, probs, mk = check_maker(path)
    return emit("pass" if status == "ready" else "fail",
                f"design maker {name}: {status}" + (f" ({len(probs)} problem(s))" if probs else
                                                    f" - {mk['primary']} / {mk['secondary']}, edges {mk['edge_rule']}"),
                f"finish it: {probs[0]}" if probs else
                f"build its pieces with a.maker(\"{name}\") - every piece of this maker carries its language",
                maker=status, problems=probs, language={k: v for k, v in mk.items() if k != "sections"})


def cmd_direction(argv):
    """the 3D lane of kit/direction.py: assets/models/direction/<Piece>.md"""
    if not argv or argv[0].startswith("--"):
        return emit("fail", "design direction: which piece?", "lune run kit design direction <Piece> [--new]")
    name = argv[0]
    folder = _arg(argv, "--dir") or os.path.join(models_root(argv), "direction")
    path = os.path.join(folder, f"{name}.md")
    import direction as D  # noqa: PLC0415  (kit/direction.py)

    args = (["new", path, "--lane", "3d", "--name", name] if "--new" in argv else ["check", path, "--lane", "3d"])
    return D.main(args)


# ---------------------------------------------------------------- exploration (C3) + originality (C4)
READ_PX = 32          # the readability test: the silhouette at 32 px across (a weapon icon / far away in game)
NOVEL_MIN = 0.12      # 1 - the cosine to the nearest past piece: under this it reads like that piece
ASPECT_BINS = (2.0, 3.0)        # long-and-thin vs compact (the grid's first axis)
SOLIDITY_BINS = (0.62, 0.78)    # open / lacy vs solid (its second axis: negative space)


DRAW_VIEWS = {"side": "a clean side view in profile with its front facing left",
              "front": "a clean front view, its face toward the viewer",
              "top": "a clean top view from directly above"}


REVIEW_VIEW = {"side": "left", "front": "front", "top": "top"}   # (look_ortho's camera for a doc's View)


def doc_view(path):
    """the view a piece is designed and traced in (its doc's preamble "View: side|front|top"; a gun: side, a shield:
    front) — side when the doc names none"""
    text = open(path, encoding="utf-8").read().split("\n## ", 1)[0]
    m = re.search(r"View:\s*(side|front|top)", text, re.I)
    return m.group(1).lower() if m else "side"


def direction_blocks(path):
    """the direction doc's directions: [{letter, name, axes{}, sheet}] + its one idea"""
    import direction as D  # noqa: PLC0415

    text = open(path, encoding="utf-8").read()
    sec = D.sections(text)
    idea = " ".join(ln.strip() for ln in sec.get("The one idea", []) if ln.strip())
    out = []
    for blk in re.split(r"^###\s+", "\n".join(sec.get("Directions", [])), flags=re.M)[1:]:
        m = re.match(r"(\w+)\s+[—-]\s+(.+)", blk.splitlines()[0])
        if not m:
            continue
        ax = re.search(r"^Axes:\s*(.+)$", blk, re.M)
        axes = dict((k.strip().lower(), v.strip()) for k, v in (kv.split("=", 1) for kv in ax.group(1).split(";")
                                                                  if "=" in kv)) if ax else {}
        sh = re.search(r"^Sheet:\s*(\S+)", blk, re.M)
        dr = re.search(r"^Draw:\s*(.+)$", blk, re.M)
        out.append({"letter": m.group(1), "name": m.group(2).strip(), "axes": axes, "sheet": sh.group(1) if sh else None,
                    "draw": dr.group(1).strip() if dr else None})
    return idea, out


def explore_prompt(idea, d, maker=None, view="side"):
    """the words for one direction's silhouettes: the idea, the direction's axes, the maker's language; a clean SIDE
    view (what the 3D route traces), never a scene"""
    ax = d["axes"]
    form = " ".join(v for v in (ax.get("material"), f"{ax['shape']}-formed" if ax.get("shape") else None) if v)
    who = f", made by {ax['maker']}" if ax.get("maker") else ""
    era = f", {ax['era']}" if ax.get("era") else ""
    mood = f", {ax['mood']} mood" if ax.get("mood") else ""
    lang = ""
    if maker:
        mats = ", ".join(re.split(r"\s+[—-]\s+", m)[0] for m in maker["materials"])
        lang = (f"; its maker's design language: {maker['primary']} forms with {maker['secondary']} accents, "
                f"{(maker['motif'] or [''])[0]}, {maker['edge_rule']} edges, {mats}")
    what = d.get("draw") or idea   # (the director's own words for the picture beat the poetic one idea: "a living
    #                                flame" drew a muzzle flash on 30 of 36; naming fire, even after "no", draws it)
    return (f"Concept design, a still studio product photograph. {what} Direction '{d['name']}': a {form} "
            f"design{who}{era}{mood}{lang}. A single object resting in the air, {DRAW_VIEWS[view]}, orthographic, the "
            f"whole object visible with a wide margin, on a plain flat mid-grey background, soft even studio lighting")


def ban_conflicts(bans, maker):
    """the doc's bans a direction's MAKER breaks by its own materials or motif (a gold-leaf maker under a 'no gold'
    ban: the direction contradicts its doc) — words of each ban found in the maker's materials / motif (pure)"""
    if not maker:
        return []
    said = " ".join(maker["materials"] + maker["motif"]).lower()
    out = []
    for b in bans:
        core = re.sub(r"\s*\(.*?\)", "", b).lower()
        core = re.sub(r"^(no|never|not)\s+", "", core).strip()
        words = [w for w in re.findall(r"[a-z]{4,}", core) if w not in ("kind", "parts", "modern")]
        if words and any(re.search(rf"\b{re.escape(w)}", said) for w in words):
            out.append(b)
    return out


def silhouette(rgb):
    """the object's mask on a plain backdrop (the border's median colour), the largest blob, holes kept"""
    import cv2  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    a = np.asarray(rgb, dtype=np.float32)
    border = np.concatenate([a[:6].reshape(-1, 3), a[-6:].reshape(-1, 3), a[:, :6].reshape(-1, 3),
                             a[:, -6:].reshape(-1, 3)])
    m = (np.abs(a - np.median(border, axis=0)).max(axis=2) > 26).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(m)
    if n < 2:
        return None
    return lab == 1 + int(np.argmax(st[1:, 4]))


def describe(mask):
    """the silhouette's traits (pure: test_design_explore.py): aspect (long side / short side of its box),
    solidity (area / convex hull: negative space), complexity (perimeter^2 / 4 pi area: 1 = a disc), holes,
    readability (IoU after a trip down to READ_PX across and back), whether it touches the frame"""
    import cv2  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    m = mask.astype(np.uint8)
    ys, xs = np.nonzero(m)
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    w, h = int(x1 - x0), int(y1 - y0)
    cs, hier = cv2.findContours(m, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    outer = max((c for i, c in enumerate(cs) if hier[0][i][3] < 0), key=cv2.contourArea)
    area = float(m.sum())
    hull = float(cv2.contourArea(cv2.convexHull(outer))) or 1.0
    per = float(cv2.arcLength(outer, True))
    holes = sum(1 for i, c in enumerate(cs) if hier[0][i][3] >= 0 and cv2.contourArea(c) > 0.002 * area)
    crop = m[y0:y1, x0:x1]
    k = READ_PX / max(w, h)
    small = cv2.resize(crop.astype(np.float32), (max(1, round(w * k)), max(1, round(h * k))),
                       interpolation=cv2.INTER_AREA)
    back = cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR) > 0.5
    inter, union = float((back & (crop > 0)).sum()), float((back | (crop > 0)).sum()) or 1.0
    H, W = m.shape
    return {"aspect": round(max(w, h) / max(1, min(w, h)), 3), "solidity": round(area / hull, 3),
            "complexity": round(per * per / (4 * np.pi * area), 2), "holes": int(holes),
            "read": round(inter / union, 3),
            "touches_frame": bool(x0 <= 1 or y0 <= 1 or x1 >= W - 1 or y1 >= H - 1),
            "fill": round(area / float(H * W), 4)}


def cell_of(t, bins=None):
    """the quality-diversity grid cell (aspect bin, solidity bin); `bins` = (aspect cuts, solidity cuts) — the
    direction's own thirds (grid_bins), so a family of pistols spreads over the grid instead of one cell"""
    ab, sb = bins or (ASPECT_BINS, SOLIDITY_BINS)
    return f"{sum(t['aspect'] > b for b in ab)}{sum(t['solidity'] > b for b in sb)}"


def grid_bins(cands):
    """the grid's cuts from the candidates themselves: the thirds of aspect and of solidity (pure)"""
    import numpy as np  # noqa: PLC0415

    if len(cands) < 6:
        return ASPECT_BINS, SOLIDITY_BINS
    a = np.array([c["aspect"] for c in cands])
    s_ = np.array([c["solidity"] for c in cands])
    return tuple(np.quantile(a, [1 / 3, 2 / 3])), tuple(np.quantile(s_, [1 / 3, 2 / 3]))


def quality(t):
    """how good a candidate is to SHOW (not its beauty: the owner judges that): readable, whole in frame, original —
    one that reads like a past piece scores down hard"""
    if t["touches_frame"] or t["fill"] < 0.02:
        return 0.0
    q = t["read"]
    nov = t.get("novelty")
    if nov is not None:
        q *= (nov / NOVEL_MIN) ** 2 if nov < NOVEL_MIN else 1.0 + min(0.5, nov)
    return round(q, 4)


def elites(cands):
    """MAP-Elites: the best candidate per grid cell, best first (pure: test_design_explore.py)"""
    best = {}
    for c in cands:
        if c["quality"] <= 0:
            continue
        k = c["cell"]
        if k not in best or c["quality"] > best[k]["quality"]:
            best[k] = c
    return sorted(best.values(), key=lambda c: -c["quality"])


def past_pieces(limit=60):
    """our own past pieces' renders (build/renders/<asset>.png, newest first): what an original must not read like"""
    folder = os.path.join(REPO, "build", "renders")
    if not os.path.isdir(folder):
        return []
    files = [os.path.join(folder, f) for f in os.listdir(folder)
             if re.fullmatch(r"[a-z0-9]+(_[a-z0-9]+){0,3}\.png", f) and not f.startswith("_")
             and not re.search(r"_(silhouette|ortho|details|edges|zebra|closeup|lookdev|labels|albedo|side|top|front)",
                               f)]
    return sorted(files, key=os.path.getmtime, reverse=True)[:limit]


def novelty(images, refs):
    """1 - the highest cosine of each image to the reference set, by SigLIP 2 AND DINOv2 (the stricter of the two:
    one encoder alone misses near-copies) -> (list of floats, the nearest reference's name per image)"""
    import numpy as np  # noqa: PLC0415

    if not refs or not images:
        return [None] * len(images), [None] * len(images)
    sys.path.insert(0, os.path.join(REPO, "kit", "vision"))
    import run as V  # noqa: PLC0415
    import torch  # noqa: PLC0415

    def dino(paths):
        model, proc = V._dino()
        _t, dev = V._torch()
        out = []
        for p in paths:
            with torch.no_grad():
                inp = proc(images=V._rgb(p), return_tensors="pt").to(dev)
                e = model(**inp).last_hidden_state[:, 0]
                out.append(torch.nn.functional.normalize(e.float(), dim=-1).cpu().numpy()[0])
        return np.stack(out)

    worst = None
    for enc in (V.embed, dino):
        s_ = enc(images) @ enc(refs).T
        worst = s_ if worst is None else np.maximum(worst, s_)
    near = worst.argmax(axis=1)
    return ([round(float(1 - worst[i, near[i]]), 4) for i in range(len(images))],
            [os.path.basename(refs[j]) for j in near])


def board(path, rows, cell=240):
    """the owner's pick board: a row per direction, its elites left to right with their traits"""
    from PIL import Image, ImageDraw  # noqa: PLC0415

    cols = max([len(r["elites"]) for r in rows] + [1])
    im = Image.new("RGB", (cell * cols + 170, (cell + 34) * len(rows) + 10), (24, 22, 26))
    d = ImageDraw.Draw(im)
    for i, r in enumerate(rows):
        y = 10 + i * (cell + 34)
        d.text((8, y + 8), f"{r['letter']} - {r['name']}"[:26], fill=(240, 220, 160))
        d.text((8, y + 26), f"{len(r['all'])} drawn", fill=(180, 180, 180))
        d.text((8, y + 42), f"{len(r['elites'])} kinds kept", fill=(180, 180, 180))
        for j, c in enumerate(r["elites"]):
            th = Image.open(c["file"]).convert("RGB")
            th.thumbnail((cell, cell))
            x = 170 + j * cell
            im.paste(th, (x + (cell - th.width) // 2, y + (cell - th.height) // 2))
            nov = "-" if c.get("novelty") is None else f"{c['novelty']:.2f}"
            d.text((x + 4, y + cell + 4), f"{r['letter']}{j + 1}  read {c['read']:.2f}  new {nov}", fill=(230, 230, 230))
            d.text((x + 4, y + cell + 18), f"aspect {c['aspect']:.1f}  solid {c['solidity']:.2f}", fill=(160, 160, 160))
    im.save(path)


def cmd_explore(argv):
    if not argv or argv[0].startswith("--"):
        return emit("fail", "design explore: which piece?", "lune run kit design explore <Piece> [--n 12]")
    name = argv[0]
    recording = "--record" in argv
    if recording and "--fresh" in argv:
        # (--fresh redraws the plates: the answers would land on pictures nobody asked about)
        return emit("fail", f"design explore {name}: --record answers the plates its packet was written for, and --fresh "
                            "would draw new ones first", f"run them apart: lune run kit design explore {name} --record "
                            "<answers.json>, then --fresh for a new round")
    folder = _arg(argv, "--dir") or os.path.join(models_root(argv), "direction")
    doc = os.path.join(folder, f"{name}.md")
    if not os.path.isfile(doc):
        return emit("fail", f"design explore: no direction doc for {name}", f"lune run kit design direction {name} --new")
    idea, dirs = direction_blocks(doc)
    import direction as D  # noqa: PLC0415

    bans = _bullets(D.sections(open(doc, encoding="utf-8").read()).get("Bans", []))
    if len(dirs) < 3 or not idea or "TODO" in idea:
        return emit("fail", f"design explore {name}: the doc needs its one idea and >= 3 directions with Axes first",
                    f"write assets/models/direction/{name}.md (lune run kit design direction {name})")
    n, seed = int(_arg(argv, "--n", "12")), int(_arg(argv, "--seed", "1"))
    out_root = os.path.join(REPO, "build", "design", name)
    makers = os.path.join(os.path.dirname(folder), "makers")
    only = [x.strip() for x in (_arg(argv, "--only") or "").split(",") if x.strip()]
    import subprocess  # noqa: PLC0415

    from PIL import Image  # noqa: PLC0415

    rows = []
    for d in dirs:
        out = os.path.join(out_root, d["letter"])
        mname = d["axes"].get("maker", "")
        mpath = os.path.join(makers, re.sub(r"[^A-Za-z0-9]", "", mname.title()) + ".md") if mname else ""
        mk = parse_maker(mpath) if mpath and os.path.isfile(mpath) else None
        prompt = explore_prompt(idea, d, mk, doc_view(doc))
        have = [f for f in os.listdir(out) if f.startswith("plate_")] if os.path.isdir(out) else []
        if must_draw(argv, len(have), n, d["letter"], only):
            r = subprocess.run(["lune", "run", "kit", "vision", "plate", prompt, "--n", str(n), "--seed", str(seed),
                                "-o", out], cwd=REPO, capture_output=True, text=True, timeout=3600)
            if not os.path.isdir(out) or not any(f.startswith("plate_") for f in os.listdir(out)):
                return emit("fail", f"design explore {name}: drawing direction {d['letter']} failed: "
                                    f"{(r.stderr or r.stdout)[-300:]}", "lune run kit vision doctor")
        cands = []
        for f in sorted(os.path.join(out, f) for f in os.listdir(out) if f.startswith("plate_")):
            mask = silhouette(Image.open(f).convert("RGB"))
            if mask is None or mask.sum() < 500:
                continue
            t = describe(mask)
            t["file"] = f
            cands.append(t)
        bins = grid_bins(cands)
        for t in cands:
            t["cell"] = cell_of(t, bins)
        rows.append({**d, "prompt": prompt, "all": cands, "maker_language": bool(mk),
                     "ban_conflicts": ban_conflicts(bans, mk)})
    # ORIGINALITY: every candidate against our own past pieces (one model load for all of them)
    allc = [c for r in rows for c in r["all"]]
    refs = past_pieces()
    nov, near = novelty([c["file"] for c in allc], refs)
    for c, v, nr in zip(allc, nov, near):
        c["novelty"], c["nearest"] = v, nr
    screen, pending, problem = screen_candidates(argv, bans, allc, out_root, name)
    if problem:
        return emit("fail", f"design explore {name} --record: {problem}",
                    f"answer {rel_repo(explore_packet_path(out_root))} again, or run explore once more for a new packet")
    for r in rows:
        for c in r["all"]:
            c["quality"] = 0.0 if c.get("bans_broken") else quality(c)
        r["elites"] = elites(r["all"])[:6]
    write_sheets(rows, folder, argv, pending)
    os.makedirs(out_root, exist_ok=True)
    bpath = os.path.join(out_root, "board.png")
    board(bpath, rows)
    with open(os.path.join(out_root, "explore.json"), "w", encoding="utf-8") as fh:
        json.dump({"piece": name, "idea": idea, "past_pieces": len(refs), "bans_screen": screen, "rows": rows}, fh,
                  indent=1, default=str)
    rel = rel_repo
    copies = [c for c in allc if c.get("novelty") is not None and c["novelty"] < NOVEL_MIN]
    banned = [c for c in allc if c.get("bans_broken")]
    clash = [f"{r['letter']} ({'; '.join(r['ban_conflicts'])})" for r in rows if r["ban_conflicts"]]
    summary = (f"design explore {name}: {len(allc)} silhouettes over {len(rows)} directions -> "
               + ", ".join(f"{r['letter']}: {len(r['elites'])} kinds" for r in rows)
               + (f"; {len(copies)} read like a past piece (scored down)" if copies else "")
               + (f"; {len(banned)} broke a ban (dropped)" if banned else "")
               + (f"; a direction's MAKER breaks the doc's bans: {', '.join(clash)}" if clash else "")
               + f"; bans: {screen}")
    if pending:
        return emit("pass", summary + " - no direction Sheet written until they are answered",
                    f"your AI client: answer {rel(pending)} (its PROMPT.md beside it), then lune run kit design explore "
                    f"{name} --record <answers.json>   (or --no-screen to go on without the screen)",
                    board=rel(bpath), packet=rel(pending))
    return emit("pass", summary, f"LOOK at {rel(bpath)}, then show the owner; record the pick in the doc's ## Pick",
                board=rel(bpath))


def must_draw(argv, have, n, letter, only):
    """does explore draw this direction's plates now? --fresh redraws (the --only directions, or all), fewer than n
    plates are topped up - and --record never draws: it answers the plates already there, whatever --n the packet's
    run used"""
    if "--record" in argv:
        return False
    return ("--fresh" in argv and (not only or letter in only)) or have < n


def screen_candidates(argv, bans, allc, out_root, name):
    """THE BANS, screened before anything reaches the board (the first board showed modern semi-autos under a "no
    modern parts" ban): each candidate asked each ban as a yes / no question; a yes drops it. The local Qwen3-VL asks
    when it is installed; without it the AI client answers a packet (--record), and until it has, no direction Sheet
    is written (an unscreened plate must not become one). --no-screen goes on without the screen, on purpose.
    -> (how they were screened, the packet waiting for answers or None, a problem with the answers or None)"""
    if not bans:
        return "no bans", None, None
    if "--no-screen" in argv:
        return "skipped (--no-screen)", None, None
    record = _arg(argv, "--record")
    if record:
        broken, problem = explore_answers(out_root, record, allc, bans)
        if problem:
            return None, None, problem
        for c in allc:
            c["bans_broken"] = broken.get(rel_repo(c["file"]), [])
        return "recorded (the AI client's answers)", None, None
    sys.path.insert(0, os.path.join(REPO, "kit", "vision"))
    import vlm  # noqa: PLC0415

    if vlm.installed():
        for c in allc:
            c["bans_broken"] = [b for b in bans if yes(vlm.ask(c["file"], ban_question(b), max_side=512,
                                                                   max_new_tokens=6))]
        return "local VLM", None, None
    return ("pending (no local VLM: the packet waits for the AI client's answers)",
            write_explore_packet(out_root, name, allc, bans), None)


def write_sheets(rows, folder, argv, pending):
    """each direction's Sheet: its best elite (--fresh redraws it) - none while the ban screen waits for answers
    -> how many were written"""
    if pending:
        return 0
    from PIL import Image  # noqa: PLC0415

    written = 0
    for r in rows:
        if r.get("elites") and r.get("sheet"):
            dst = r["sheet"] if os.path.isabs(r["sheet"]) else os.path.join(os.path.dirname(folder), r["sheet"])
            if "--fresh" in argv or not os.path.isfile(dst):
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                Image.open(r["elites"][0]["file"]).save(dst)
                written += 1
    return written


def file_sha(path):
    try:
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()
    except OSError:
        return None


def rel_repo(path):
    return os.path.relpath(path, REPO).replace(os.sep, "/")


def explore_packet_path(out_root):
    return os.path.join(out_root, "bans_packet.json")


def write_explore_packet(out_root, name, allc, bans):
    """the ban screen for the AI client when no local VLM is installed: every candidate plate and every ban as a yes /
    no question (bans_packet.json + bans_PROMPT.md in build/design/<Piece>/) -> the packet's path"""
    os.makedirs(out_root, exist_ok=True)
    packet = {
        "piece": name,
        "candidates": [{"id": i, "file": rel_repo(c["file"]), "sha256": file_sha(c["file"])}
                       for i, c in enumerate(allc)],
        "bans": [{"id": i, "ban": b, "question": ban_question(b)} for i, b in enumerate(bans)],
        "answer": {"broken": {"<candidate id>": "[the ids of the bans that candidate breaks]"}},
    }
    path = explore_packet_path(out_root)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(packet, fh, indent=1)
    lines = [f"# Ban screen - {name}", "",
             "Look at each candidate picture below. For each ban, answer its question about that picture.",
             "Write a JSON file listing ONLY the candidates that break at least one ban, by id:",
             "", '    {"broken": {"3": [0], "7": [0, 2]}}', "",
             "(no candidate breaks any ban: {\"broken\": {}}). Then run:", "",
             f"    lune run kit design explore {name} --record <that file>", "", "## Bans", ""]
    lines += [f"- {q['id']}: {q['question']}" for q in packet["bans"]]
    lines += ["", "## Candidates", ""] + [f"- {c['id']}: {c['file']}" for c in packet["candidates"]]
    with open(os.path.join(out_root, "bans_PROMPT.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    return path


def explore_answers(out_root, answers_path, allc, bans):
    """the AI client's answers to the ban packet -> ({candidate file: [bans it breaks]}, problem). Refused: answers for
    another set of plates or bans (the packet is stale), an id the packet does not hold, a value that is no id list"""
    path = explore_packet_path(out_root)
    if not os.path.isfile(path):
        return {}, "no ban packet: run explore once without --record to write it"
    try:
        with open(path, encoding="utf-8") as fh:
            packet = json.load(fh)
        with open(answers_path, encoding="utf-8") as fh:
            answers = json.load(fh)
    except (OSError, ValueError) as e:
        return {}, f"cannot read the packet or the answers ({e})"
    files = {c["id"]: c["file"] for c in packet.get("candidates", [])}
    asked = {c["file"]: c.get("sha256") for c in packet.get("candidates", [])}
    now = {rel_repo(c["file"]): file_sha(c["file"]) for c in allc}
    if asked != now or [q.get("ban") for q in packet.get("bans", [])] != list(bans):
        return {}, ("the packet is for other plates or other bans (explore drew or changed them since): answer the "
                    "new packet")
    broken = answers.get("broken") if isinstance(answers, dict) else None
    if not isinstance(broken, dict):
        return {}, 'the answers need {"broken": {"<candidate id>": [ban ids]}}'
    out = {}
    for key, ban_ids in broken.items():
        cid = int(key) if isinstance(key, str) and key.isdigit() else None
        good, bad = valid_ids(ban_ids, range(len(bans)))
        if cid not in files or bad:
            return {}, f"candidate {key!r}: {'no such candidate' if cid not in files else f'no such ban id(s) {bad}'}"
        out[files[cid]] = [bans[i] for i in good]
    return out, None


def valid_ids(value, valid):
    """a list of integer ids, each one of `valid` (true / false are no ids) -> (the ids, the bad entries)"""
    if not isinstance(value, list):
        return [], [value]
    bad = [i for i in value if isinstance(i, bool) or not isinstance(i, int) or i not in valid]
    return [i for i in value if not (isinstance(i, bool) or not isinstance(i, int) or i not in valid)], bad


# ---------------------------------------------------------------- the concept sheet (C5)
VIEW_WORDS = {
    "side": "a clean side view in profile with its front facing left",
    "front": "seen from directly in front, looking straight at its muzzle end, an orthographic front view",
    "top": "seen from directly above, an orthographic top view, its front facing left",
}


def concept_prompt(view, what):
    """a view of THE SAME design as the reference picture (FLUX.2 klein image conditioning) — the words keep the
    object, the view changes"""
    return (f"The same weapon exactly as in the reference image, {what}: every part, proportion, colour and material "
            f"the same, {VIEW_WORDS[view]}, the whole object visible with a wide margin, on a plain flat mid-grey "
            f"background, soft even studio lighting, a still studio product photograph")


def best_match(cands, ref_mask, by="length"):
    """the candidate whose silhouette lies best on the reference's (aligned by one axis, mirrored if that fits
    better) -> (file, iou) — the redraw that kept the design (pure on masks: test_design_concept.py)"""
    sys.path.insert(0, HERE)
    import look_silhouette as LS  # noqa: PLC0415

    best = (None, 0.0)
    for f, m in cands:
        for flip in (False, True):
            r_ = ref_mask[:, ::-1] if flip else ref_mask
            built, _s = LS.align(r_, m, by)
            iou = float((built & r_).sum()) / max(1.0, float((built | r_).sum()))
            if iou > best[1]:
                best = (f, round(iou, 3))
    return best


def copies_base(m, base_m, iou_max=0.75, cover_max=0.8):
    """a "turned" view that is the base view again: its outline lies on the base's (IoU > iou_max), or it COVERS most
    of the base's (> cover_max of the base's pixels, aligned, mirrored if that fits better) — the base redrawn with
    something added: the Lantern Hook's "front" was its side plus a disc, IoU under 0.75, kept as a front (pure:
    test_design_concept.py)"""
    sys.path.insert(0, HERE)
    import look_silhouette as LS  # noqa: PLC0415

    pairs = []
    for flip in (False, True):
        r_ = base_m[:, ::-1] if flip else base_m
        if m.shape == r_.shape:   # (as drawn: the generator keeps the reference's frame — an added part widens the
            pairs.append((m, r_))  #  outline's box and throws the box alignment off)
        pairs.append((LS.align(r_, m, "length")[0], r_))
    for built, r_ in pairs:
        inter = float((built & r_).sum())
        if inter / max(1.0, float((built | r_).sum())) > iou_max or inter / max(1.0, float(r_.sum())) > cover_max:
            return True
    return False


def _plates(prompt, src, n, seed, out):
    import subprocess  # noqa: PLC0415

    subprocess.run(["lune", "run", "kit", "vision", "plate", prompt, "--from", src, "--n", str(n), "--seed", str(seed),
                    "-o", out], cwd=REPO, capture_output=True, text=True, timeout=3600)
    return sorted(os.path.join(out, f) for f in os.listdir(out) if f.startswith("plate_")) if os.path.isdir(out) else []


def cmd_concept(argv):
    if not argv or argv[0].startswith("--") or "--from" not in argv:
        return emit("fail", "design concept: needs <Piece> --from <the picked silhouette>",
                    "lune run kit design concept <Piece> --from build/design/<Piece>/<X>/plate_NNN.png")
    from PIL import Image  # noqa: PLC0415

    name, src = argv[0], _arg(argv, "--from")
    if not os.path.isfile(src):
        return emit("fail", f"design concept: no picture {src}", "the picked candidate's file (explore.json)")
    what = _arg(argv, "--what") or "the weapon"
    n, seed = int(_arg(argv, "--n", "4")), int(_arg(argv, "--seed", "1"))
    out_root = os.path.join(REPO, "build", "design", name, "concept")
    dst = os.path.join(models_root(argv), "direction")
    os.makedirs(dst, exist_ok=True)
    pick = silhouette(Image.open(src).convert("RGB"))
    views, checks = {}, {}
    doc = os.path.join(dst, f"{name}.md")
    base = doc_view(doc) if os.path.isfile(doc) else "side"   # (the view it was designed in: a gun's side, a shield's front)
    # 1. the BASE view redrawn clean, kept only when its outline still lies on the pick's
    side_c = [(f, silhouette(Image.open(f).convert("RGB")))
              for f in _plates(concept_prompt(base, what), src, n, seed, os.path.join(out_root, base))]
    side_c = [(f, m) for f, m in side_c if m is not None and not describe(m)["touches_frame"]]
    f, iou = best_match(side_c, pick) if side_c else (None, 0.0)
    if f is None or iou < 0.80:
        f, iou = src, 1.0   # (no redraw kept the design: the pick itself is the base view)
    views[base], checks["side_vs_pick_iou"] = f, iou
    side_m = silhouette(Image.open(f).convert("RGB"))
    sd = describe(side_m)
    # 2. the other two views from the base (the same design turned): kept by how well their size agrees with it
    for view in [v for v in ("side", "front", "top") if v != base]:
        cands = []
        for g in _plates(concept_prompt(view, what), views[base], n, seed, os.path.join(out_root, view)):
            m = silhouette(Image.open(g).convert("RGB"))
            if m is None or describe(m)["touches_frame"]:
                continue
            t = describe(m)
            if copies_base(m, side_m):   # (the "turned" view is the side again: FLUX.2 klein often keeps the
                continue                 #  reference's view — LanternPistol's "top"; LanternHook's "front" + a disc)
            ys, xs = m.nonzero()
            w, h = xs.max() - xs.min() + 1, ys.max() - ys.min() + 1
            # front: an upright, narrow object (taller than wide); top: as long as the side, much thinner
            if base != "side":   # (no size prior for a piece designed from its front / top: the first that turned)
                score = 1.0
            elif view == "front":
                score = 1.0 / (1.0 + abs(w / h - 0.45))
            else:
                score = 1.0 / (1.0 + abs(t["aspect"] - 2.0 * sd["aspect"]))
            cands.append((score, g))
        if cands:
            views[view] = max(cands)[1]
            checks[f"{view}_score"] = round(max(cands)[0], 3)
    # 3. a three-quarter look (the kit's concept three_quarter, from the side)
    import subprocess  # noqa: PLC0415

    tq = os.path.join(out_root, "three_quarter.png")
    subprocess.run(["lune", "run", "kit", "vision", "concept", f"{what}", "--sheet", "three_quarter", "--from",
                    views[base], "-o", tq], cwd=REPO, capture_output=True, text=True, timeout=1800)
    if os.path.isfile(tq):
        views["three_quarter"] = tq
    # the SHEET the 3D route builds from: the views side by side + a record
    for v, p in views.items():
        Image.open(p).convert("RGB").save(os.path.join(dst, f"{name}.{v}.png"))
    cell = 512
    order = [v for v in ("side", "front", "top", "three_quarter") if v in views]
    sheet = Image.new("RGB", (cell * len(order), cell), (128, 128, 128))
    for i, v in enumerate(order):
        im = Image.open(views[v]).convert("RGB")
        im.thumbnail((cell, cell))
        sheet.paste(im, (i * cell + (cell - im.width) // 2, (cell - im.height) // 2))
    spath = os.path.join(dst, f"{name}.concept.png")
    sheet.save(spath)
    rec = {"piece": name, "from": src, "views": {v: os.path.join(dst, f"{name}.{v}.png") for v in views},
           "checks": checks, "note": "a CONCEPT drawn to agree a design; sizes come from the brief and the maker, "
                                     "never measured off a generated picture alone"}
    with open(os.path.join(dst, f"{name}.concept.json"), "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=1)
    rel = lambda q: os.path.relpath(q, REPO).replace(os.sep, "/")  # noqa: E731
    missing = [v for v in ("side", "front", "top") if v not in views]
    return emit("pass",
                f"design concept {name}: {', '.join(order)} ({base} kept the pick at IoU {checks['side_vs_pick_iou']:.2f})"
                + (f"; no usable {', '.join(missing)} view (the generator kept the {base}): the depths come from the "
                   "director's section plan and the maker's language" if missing else ""),
                f"LOOK at {rel(spath)}; then trace the {base}: lune run kit trace {rel(os.path.join(dst, name + '.' + base + '.png'))}"
                f" --name {name.lower()}_side --part-text ...",
                sheet=rel(spath), views={v: rel(p) for v, p in rec["views"].items()})


# ---------------------------------------------------------------- the director's review (C6)
DETAIL_TOL = 12.0     # the build's detail share may sit this many points off the maker's


def ban_question(ban):
    """a ban as a yes/no question about the picture (yes = broken): "no gold (gold belongs to ...)" ->
    "Does this object have gold?" (pure: test_design_review.py)"""
    b = re.sub(r"\s*\(.*?\)", "", ban).strip().rstrip(".")
    b = re.sub(r"^(no|never|not)\s+", "", b, flags=re.I)
    b = re.sub(r"\s+of any kind$", "", b, flags=re.I)
    return f"Look at this object. Does it have {b}? Answer only yes or no."


def pillar_question(pillar, views=1):
    """a pillar as a yes/no question (no = missed); views > 1: the picture is a sheet of views of ONE object"""
    p = pillar.strip().rstrip(".")
    lead = ("These are views of one single object (side, front and top). Looking at all of them together, is this "
            "true of the object" if views > 1 else "Look at this object. Is this true of it")
    return f"{lead}: {p}? Answer only yes or no."


def views_sheet(paths, out, cell=512):
    """the review's VIEWS of one object side by side on grey (an abstract pillar — "seen from every side", "on every
    part" — cannot be judged from one side view: the first review missed both on the lantern pistol)"""
    from PIL import Image  # noqa: PLC0415

    ims = []
    for p in paths:
        rgba = Image.open(p).convert("RGBA")
        flat = Image.new("RGB", rgba.size, (128, 128, 128))
        flat.paste(rgba, mask=rgba.split()[3])
        flat.thumbnail((cell, cell))
        ims.append(flat)
    sheet = Image.new("RGB", (cell * len(ims), cell), (128, 128, 128))
    for i, im in enumerate(ims):
        sheet.paste(im, (i * cell + (cell - im.width) // 2, (cell - im.height) // 2))
    sheet.save(out)
    return out


def yes(answer):
    return bool(re.match(r"\s*\**\s*yes\b", answer or "", re.I))


def detail_share(rgb, mask):
    """the share of the object's surface that carries detail: TEED line pixels (kit vision edges) dilated into
    little regions, over the object's area (%) — what a director means by 'busy' vs 'quiet'"""
    import cv2  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    sys.path.insert(0, os.path.join(REPO, "kit", "vision"))
    import run as V  # noqa: PLC0415

    e = V.edges(rgb) > 0.6
    k = max(3, int(0.012 * max(mask.shape)))
    busy = cv2.dilate(e.astype(np.uint8), np.ones((k, k), np.uint8)) > 0
    inner = cv2.erode(mask.astype(np.uint8), np.ones((k, k), np.uint8)) > 0   # (the outline is not detail)
    return round(100.0 * float((busy & inner).sum()) / max(1.0, float(inner.sum())), 1)


def judge(findings):
    """the review's fix list, worst first, from its findings (pure: test_design_review.py)"""
    fixes = []
    f = findings
    for b in f.get("bans_broken", []):
        fixes.append(f"BAN broken: {b} — remove it")
    if f.get("silhouette_iou") is not None and f["silhouette_iou"] < 0.75:
        fixes.append(f"the silhouette strays from the picked sheet (overlap {f['silhouette_iou']:.2f} < 0.75) — "
                     "retrace / rebuild the parts that differ (kit look silhouette shows where)")
    for p in f.get("pillars_missed", []):   # (judged by a small local vision model on renders: a pointer, not a gate —
        #                                       the owner's verdict decides; ask it an open question to see why)
        fixes.append(f"PILLAR missed (advisory: the vision model's read): {p}")
    if f.get("read") is not None and f["read"] < 0.80:
        fixes.append(f"hard to read at {READ_PX} px (outline kept {f['read']:.2f} < 0.80) — fewer thin spikes, "
                     "bolder primary shapes")
    if f.get("novelty") is not None and f["novelty"] < NOVEL_MIN:
        fixes.append(f"reads like a past piece ({f.get('nearest')}, distance {f['novelty']:.2f} < {NOVEL_MIN}) — "
                     "change its primary shape, not its colour")
    want, got = f.get("detail_target"), f.get("detail_share")
    if want is not None and got is not None and abs(got - want) > DETAIL_TOL:
        fixes.append(f"detail share {got:.0f}% vs the maker's {want:.0f}% — "
                     + ("too busy: give the eye quiet areas" if got > want else "too plain: add the maker's motif"))
    return fixes


def review_target(folder, name, doc, chosen):
    """the picture a build answers to: the PICK — its concept view (kit design concept: the picked plate redrawn,
    <Piece>.<view>.png) — else the picked direction's Sheet. The Sheet is that direction's BEST-scored plate, not
    necessarily the pick: the Lantern Hook's pick was B's second, and a faithful build measured against B's first read
    0.38 (pure: test_design_review.py)"""
    concept = os.path.join(folder, f"{name}.{doc_view(doc)}.png")
    if os.path.isfile(concept):
        return concept
    return os.path.join(os.path.dirname(folder), chosen["sheet"]) if chosen else None


def cmd_review_record(argv):
    """--record <verdict.json>: validate an agent-supplied verdict against the packet and store it into the review JSON.
    The verdict must be a JSON object with:
      bans_broken:    list of ban IDs (integers) from the packet's questions.bans
      pillars_missed: list of pillar IDs (integers) from the packet's questions.pillars
    Any ID not present in the packet is rejected (a ban the agent invented)."""
    name = argv[0]
    asset = _arg(argv, "--asset")
    record_path = _arg(argv, "--record")
    if not (name and asset and record_path):
        return emit("fail", "design review --record: needs <Piece> --asset <name> --record <verdict.json>",
                    "lune run kit design review <Piece> --asset <name> --record verdict.json")
    out_dir = os.path.join(REPO, "build", "design", name)
    packet_path = os.path.join(out_dir, f"review_{asset}_packet.json")
    review_path = os.path.join(out_dir, f"review_{asset}.json")
    if not os.path.isfile(packet_path):
        return emit("fail", f"design review --record: no packet for {asset}",
                    f"lune run kit design review {name} --asset {asset} --packet")
    if not os.path.isfile(record_path):
        return emit("fail", f"design review --record: verdict file not found: {record_path}", "write the verdict JSON")
    with open(packet_path, encoding="utf-8") as fh:
        packet = json.load(fh)
    try:
        with open(record_path, encoding="utf-8") as fh:
            verdict = json.load(fh)
    except ValueError as e:
        return emit("fail", f"design review --record: the verdict is not JSON ({e})", "write the verdict JSON")
    if not isinstance(verdict, dict) or "bans_broken" not in verdict or "pillars_missed" not in verdict:
        # (both answers, each a list - [] when none: an empty object is no answer, never "clean")
        return emit("fail", "design review --record: the verdict must be a JSON object with both answers",
                    '{"bans_broken": [ban ids], "pillars_missed": [pillar ids]}   ([] when none)')
    if packet.get("build_sha256") and file_sha(os.path.join(REPO, packet.get("build", ""))) != packet["build_sha256"]:
        return emit("fail", f"design review --record: {asset} was rebuilt since the packet was written - these answers "
                            "are about the old build", f"lune run kit design review {name} --asset {asset}   (a new packet)")
    valid_ban_ids = {q["id"] for q in packet["questions"]["bans"]}
    valid_pillar_ids = {q["id"] for q in packet["questions"]["pillars"]}
    ban_ids, bad_bans = valid_ids(verdict.get("bans_broken", []), valid_ban_ids)
    pillar_ids, bad_pillars = valid_ids(verdict.get("pillars_missed", []), valid_pillar_ids)
    bad = bad_bans + bad_pillars
    if bad:
        return emit("fail",
                    f"design review --record: verdict contains IDs not in the packet: {bad}",
                    "use only the IDs from the packet's questions.bans / questions.pillars lists")
    bans_list = [packet["questions"]["bans"][i]["ban"] for i in ban_ids]
    pillars_list = [packet["questions"]["pillars"][i]["pillar"] for i in pillar_ids]
    if os.path.isfile(review_path):
        with open(review_path, encoding="utf-8") as fh:
            f = json.load(fh)
    else:
        f = {"asset": asset, "piece": name}
    f["bans_broken"] = bans_list
    f["pillars_missed"] = pillars_list
    fixes = judge(f)
    f["fixes"] = fixes
    with open(review_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(f, fh, indent=1)
    return emit("pass" if not fixes else "fail",
                f"design review {name} ({asset}) recorded: " + (
                    f"{len(fixes)} fix(es): " + "; ".join(fixes[:3]) if fixes else
                    "clean against the direction — the owner's verdict decides"),
                "one fix list, one round: fix these, rebuild, review once more; then the owner" if fixes else
                f"record the verdict: kit verdict asset {asset} <0-10> \"...\"",
                review=f)


def cmd_review(argv):
    if not argv or argv[0].startswith("--") or ("--asset" not in argv and "--record" not in argv):
        return emit("fail", "design review: needs <Piece> --asset <built asset>",
                    "lune run kit design review <Piece> --asset <name>")
    if "--record" in argv:
        return cmd_review_record(argv)
    name, asset = argv[0], _arg(argv, "--asset")
    folder = _arg(argv, "--dir") or os.path.join(models_root(argv), "direction")
    doc = os.path.join(folder, f"{name}.md")
    if not os.path.isfile(doc):
        return emit("fail", f"design review: no direction doc for {name}", f"lune run kit design direction {name}")
    import direction as D  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    sec = D.sections(open(doc, encoding="utf-8").read())
    pillars, bans = _bullets(sec.get("Pillars", [])), _bullets(sec.get("Bans", []))
    pick = " ".join(sec.get("Pick", [])).strip()
    idea, dirs = direction_blocks(doc)
    m = re.match(r"picked:\s*([A-Z])", pick)
    chosen = next((d for d in dirs if m and d["letter"] == m.group(1)), None)
    sheet = _arg(argv, "--sheet") or review_target(folder, name, doc, chosen)
    blend = os.path.join(build_root(argv), "models", f"{asset}.blend")
    if not os.path.isfile(blend):
        return emit("fail", f"design review: no build of {asset}", f"lune run kit asset {asset}")
    # the build from the view it was DESIGNED in (the doc's View: a shield is judged on its face — its side is an
    # edge, read 0.74 "hard to read at 32 px"), orthographic (look_ortho), the whole asset
    view = _arg(argv, "--view") or REVIEW_VIEW[doc_view(doc)]
    import subprocess  # noqa: PLC0415

    import look  # noqa: PLC0415

    man = json.load(open(os.path.join(build_root(argv), "models", f"{asset}.manifest.json"), encoding="utf-8"))
    bounds = man.get("part_bounds") or {}
    words = [w for w in (_arg(argv, "--part") or "").split(",") if w]
    hits = [n for n in bounds if not words or any(w.lower() in n.lower() for w in words)]
    lo = [min(bounds[n][0][i] for n in hits) for i in range(3)]
    hi = [max(bounds[n][1][i] for n in hits) for i in range(3)]
    out_dir = os.path.join(REPO, "build", "design", name)
    os.makedirs(out_dir, exist_ok=True)
    side = os.path.join(out_dir, f"review_{asset}_side.png")
    subprocess.run([look.blender(), "-b", blend, "-P", os.path.join(REPO, "kit", "blender", "look_ortho.py"), "--",
                    side, ",".join(map(str, lo)), ",".join(map(str, hi)), "--view", view,
                    "--samples", "32", "--px", "1200"], capture_output=True, text=True, timeout=1800)
    if not os.path.isfile(side):
        return emit("fail", "design review: the side render failed", "read the error above")
    rgba = Image.open(side).convert("RGBA")
    flat = Image.new("RGB", rgba.size, (128, 128, 128))
    flat.paste(rgba, mask=rgba.split()[3])
    flat_path = side.replace(".png", "_grey.png")
    flat.save(flat_path)
    mask = np.asarray(rgba)[..., 3] > 127
    f = {"asset": asset, "piece": name, "view": view,
         "render": os.path.relpath(flat_path, REPO).replace(os.sep, "/")}
    f.update({k: describe(mask)[k] for k in ("read", "aspect", "solidity")})
    if sheet and os.path.isfile(sheet):
        import look_silhouette as LS  # noqa: PLC0415

        ref = silhouette(Image.open(sheet).convert("RGB"))
        best = 0.0
        for flip in (False, True):
            r_ = ref[:, ::-1] if flip else ref
            built, _s = LS.align(r_, mask, "length")
            best = max(best, float((built & r_).sum()) / max(1.0, float((built | r_).sum())))
        f["silhouette_iou"] = round(best, 3)
    refs = [p for p in past_pieces() if not os.path.basename(p).startswith(asset)]
    nov, near = novelty([flat_path], refs)
    f["novelty"], f["nearest"] = nov[0], near[0]
    mk_name = (chosen or {}).get("axes", {}).get("maker", "")
    mpath = os.path.join(os.path.dirname(folder), "makers", re.sub(r"[^A-Za-z0-9]", "", mk_name.title()) + ".md")
    if mk_name and os.path.isfile(mpath):
        f["detail_target"] = parse_maker(mpath)["detail_share"]
    # the detail share on a CLAY render: geometry only — a scanned patina's mottle is texture, not detail (the first
    # review of the lantern pistol counted its rust scan: 69% "busy")
    clay = side.replace(".png", "_clay.png")
    subprocess.run([look.blender(), "-b", blend, "-P", os.path.join(REPO, "kit", "blender", "look_ortho.py"), "--",
                    clay, ",".join(map(str, lo)), ",".join(map(str, hi)), "--view", view,
                    "--samples", "32", "--px", "1200", "--clay"], capture_output=True, text=True, timeout=1800)
    if os.path.isfile(clay):
        crgba = Image.open(clay).convert("RGBA")
        cflat = Image.new("RGB", crgba.size, (128, 128, 128))
        cflat.paste(crgba, mask=crgba.split()[3])
        f["detail_share"] = detail_share(cflat, np.asarray(crgba)[..., 3] > 127)
    else:
        f["detail_share"] = detail_share(flat, mask)
    sys.path.insert(0, os.path.join(REPO, "kit", "vision"))
    import vlm  # noqa: PLC0415

    # the FRONT and TOP too: bans and pillars judged on the sheet of all three views
    others = []
    for v in ("front", "top"):
        vp = os.path.join(out_dir, f"review_{asset}_{v}.png")
        subprocess.run([look.blender(), "-b", blend, "-P", os.path.join(REPO, "kit", "blender", "look_ortho.py"), "--",
                        vp, ",".join(map(str, lo)), ",".join(map(str, hi)), "--view", v, "--samples", "32", "--px",
                        "900"], capture_output=True, text=True, timeout=1800)
        if os.path.isfile(vp):
            others.append(vp)
    sheet_path = views_sheet([side] + others, os.path.join(out_dir, f"review_{asset}_views.png"))
    nv = 1 + len(others)
    f["views"] = os.path.relpath(sheet_path, REPO).replace(os.sep, "/")

    use_packet = "--packet" in argv or "--no-vlm" in argv or not vlm.installed()
    if use_packet:
        # --- PACKET MODE: write the questions and images for the agent to answer ---
        questions = {
            "bans": [{"id": i, "ban": b, "question": ban_question(b)} for i, b in enumerate(bans)],
            "pillars": [{"id": i, "pillar": p, "question": pillar_question(p, nv)} for i, p in enumerate(pillars)],
        }
        packet_path = os.path.join(out_dir, f"review_{asset}_packet.json")
        with open(packet_path, "w", encoding="utf-8", newline="\n") as fh:
            # (the build the views were made from: --record refuses answers once the asset is rebuilt)
            json.dump({"asset": asset, "piece": name, "views": f["views"],
                       "build": rel_repo(blend), "build_sha256": file_sha(blend),
                       "questions": questions,
                       "answer_schema": {
                           "bans_broken": "list of ban ids (from questions.bans) where the answer to the question is yes",
                           "pillars_missed": "list of pillar ids (from questions.pillars) where the answer is no",
                       }}, fh, indent=1)
        # a PROMPT.md alongside the packet so the agent knows exactly what to do
        prompt_path = os.path.join(out_dir, "PROMPT.md")
        rel_views = f["views"]
        rel_packet = os.path.relpath(packet_path, REPO).replace(os.sep, "/")
        with open(prompt_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(f"# Design review — {name} ({asset})\n\n"
                     f"Look at the views sheet: `{rel_views}`\n\n"
                     "For each question below answer only **yes** or **no**:\n\n"
                     "**Bans** (yes = broken — the object shows this banned thing):\n")
            for q in questions["bans"]:
                fh.write(f"- [{q['id']}] {q['question']}\n")
            fh.write("\n**Pillars** (yes = present — the object shows this required feature):\n")
            for q in questions["pillars"]:
                fh.write(f"- [{q['id']}] {q['question']}\n")
            fh.write(f"\nRecord your answer:\n\n"
                     f"```\nlune run kit design review {name} --asset {asset} --record <verdict.json>\n```\n\n"
                     f"The verdict JSON shape (from `questions` in {rel_packet}):\n\n"
                     f"```json\n{{\"bans_broken\": [<ban ids>], \"pillars_missed\": [<pillar ids>]}}\n```\n")
        f["bans_broken"] = None   # not yet answered
        f["pillars_missed"] = None
        with open(os.path.join(out_dir, f"review_{asset}.json"), "w", encoding="utf-8", newline="\n") as fh:
            json.dump(f, fh, indent=1)
        rel_prompt = os.path.relpath(prompt_path, REPO).replace(os.sep, "/")
        return emit("pass",
                    f"design review {name} ({asset}): packet written (VLM absent or --packet); "
                    f"{len(bans)} ban(s), {len(pillars)} pillar(s) to answer",
                    f"LOOK at {rel_views}; read {rel_prompt}; then: "
                    f"lune run kit design review {name} --asset {asset} --record <verdict.json>",
                    packet=os.path.relpath(packet_path, REPO).replace(os.sep, "/"),
                    prompt=rel_prompt)

    # --- VLM MODE (unchanged path) ---
    f["bans_broken"] = [b for b in bans if yes(vlm.ask(sheet_path, ban_question(b), max_side=1536, max_new_tokens=8))]
    f["pillars_missed"] = [p for p in pillars if not yes(vlm.ask(sheet_path, pillar_question(p, nv), max_side=1536,
                                                                   max_new_tokens=8))]
    fixes = judge(f)
    f["fixes"] = fixes
    with open(os.path.join(out_dir, f"review_{asset}.json"), "w", encoding="utf-8") as fh:
        json.dump(f, fh, indent=1)
    return emit("pass" if not fixes else "fail",
                f"design review {name} ({asset}): " + (f"{len(fixes)} fix(es): " + "; ".join(fixes[:3]) if fixes else
                                                       "clean against the direction — the owner's verdict decides"),
                "one fix list, one round: fix these, rebuild, review once more; then the owner" if fixes else
                f"show the owner {f['render']}; record the verdict (kit verdict asset {asset} <0-10> \"...\")",
                review=f)


def main(argv):
    cmds = {"maker": cmd_maker, "direction": cmd_direction, "explore": cmd_explore, "concept": cmd_concept,
            "review": cmd_review}
    if not argv or argv[0] not in cmds:
        return emit("fail", "design: usage: direction <Piece> [--new] | maker <Maker> [--new] | explore <Piece> [--n 12] | "
                            "review <Piece> --asset <name>",
                    "lune run kit design direction <Piece> --new")
    return cmds[argv[0]](argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
