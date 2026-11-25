"""judge.py — the INDEPENDENT judge for hero / aaa models. The builder never grades its own work.

    python kit/blender/judge.py packet <asset>             build/judge/<asset>/: sheet.png, sheet_2.png ... (each within a
                                                            vision model's limits: seen unshrunk) + PROMPT.md
    python kit/blender/judge.py record <asset> [verdict]   validate the verdict(s) -> assets/models/<asset>.judge.json; a PANEL:
                                                            every build/judge/<asset>/verdict*.json for this build, the
                                                            median per criterion, the spread between judges reported
    python kit/blender/judge.py anchor <asset> <owner>     keep the asset's current hero render as an owner-graded anchor
    python kit/blender/judge_pair.py pair|tally <asset>    PAIRWISE: two builds side by side, six views + regions, blind
                                                            (kit judge <asset> --pair / --tally)

Why: a model that builds an asset and then scores it is satisfied too early (it wants to finish). The judge is a
FRESH context (a subagent, another session, another model) that sees the packet — the reference, the model, the
close-ups and the owner's graded anchors — and scores a fixed rubric. Its verdict is tied to the exact build it saw
(build_id = hash of the shipped meshes + maps); a later build needs a new verdict. Plain Python + Pillow.
"""

import datetime
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

KIT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
REPO = os.path.dirname(KIT)
TIERS = {"prop": 55, "hero": 75, "aaa": 88}
# WHAT A JUDGE'S EYES TAKE IN: a vision model shrinks any image past ~1.15 megapixels or 1568 px on its long edge
# (Anthropic's vision docs). The one 2400 x 2220 sheet reached the judges at ~46 %: the 640 x 480 close-ups at ~58 % of
# their own pixels — modelled stipple, edge wear, pins and letters fell under a pixel and were judged "missing"
# (the Glock, 2026-10-09). Every packet image stays inside both limits: the judges see the renders' own pixels.
VISION_MAX_PX = 1_150_000
VISION_MAX_EDGE = 1568

# The rubric: ten criteria, 0-10 each, total = /100. Level descriptions keep different judges on one scale.
RUBRIC = [
    ("silhouette", "Silhouette & proportions", "outline, length:height, angles, keel/stock/muzzle shapes — against the reference"),
    ("massing", "Primary forms", "the big shapes and their hierarchy; layered volumes, not one box with things glued on"),
    ("secondary", "Secondary forms", "panels, insets, plates, clamps, rails, recesses — how the big shapes are broken up"),
    ("tertiary", "Tertiary detail", "screws, vents, fins, small lights, seams, text — density, scale and placement"),
    ("distribution", "Detail rhythm", "busy areas vs intentional rest areas; no dead expanses, no noise everywhere"),
    ("materials", "Material read", "metal / paint / rubber / glass readable at a glance; roughness + value separation"),
    ("surface", "Surface story", "wear, chips, grime, scratches where use would put them — believable, not noise"),
    ("accents", "Accent lights & colour", "emissives / accent colour placed with intent and restraint, glowing correctly"),
    ("markings", "Markings & typography", "maker text, serials, stencils: crisp, well placed, scaled like the reference"),
    ("craft", "Craft (no defects)", "nothing floating, clipping, stretched, smeared, broken shading or artifacts; 10 = none visible"),
]
LEVELS = """10 = indistinguishable from a shipped AAA hero asset (Halo Infinite / Destiny 2 / Apex weapon art) and matches
     or beats the reference on this criterion, including in the close-ups
 9 = AAA quality with one minor flaw a trained eye finds
 8 = strong, clearly professional; a couple of visible gaps against the reference
 7 = good indie quality; noticeably simpler than the reference
 5 = competent but plain / generic
 3 = blockout-level
 0 = missing or broken"""


def _font(size):
    for f in ("arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _out(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def brief_reference(asset, root=REPO):
    """the reference picture the BRIEF names as its quality bar ("- quality bar: ... <path>.png ..."): the first
    picture path on that line that exists (relative to the project root), or None. A build that never set
    Asset(ref_image=) was judged against nothing - celestial_sword's first judge (2026-11-20) marked the owner's own
    picked ring guard down as a 'steering wheel' with no picture of the pick in its packet."""
    import re  # noqa: PLC0415

    brief = os.path.join(root, "assets", "models", f"{asset}.brief.md")
    try:
        with open(brief, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return None
    for line in text.splitlines():
        if re.match(r"^\s*-\s*quality bar\s*:", line, re.I):
            for p in re.findall(r"[\w./\\-]+\.(?:png|jpe?g|webp)", line, re.I):
                if os.path.isfile(os.path.join(root, p)):
                    return p.replace("\\", "/")
    return None


def _manifest(asset):
    path = os.path.join(REPO, "build", "models", f"{asset}.manifest.json")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        m = json.load(fh)
    if not m.get("reference_image"):   # (no Asset(ref_image=): the brief's quality-bar picture, said in the packet)
        ref = brief_reference(asset)
        if ref:
            m["reference_image"], m["reference_from"] = ref, "the brief's quality bar"
    return m


def _anchors(folder=None, private=True):
    """the owner's graded anchors: the shared index (committed, copied to every project) and — unless private=False —
    this project's PRIVATE ones (anchors/private: a private asset's render never leaves the machine it was made on)"""
    folder = folder or os.path.join(KIT, "anchors")
    out = []
    for path in [os.path.join(folder, "anchors.json")] + ([os.path.join(folder, "private", "anchors.json")] if private else []):
        try:
            with open(path, encoding="utf-8") as fh:
                items = json.load(fh)
        except (OSError, ValueError):
            continue
        out += [a for a in items if isinstance(a, dict)] if isinstance(items, list) else []
    return sorted(out, key=lambda a: str(a.get("at") or ""))   # (oldest first, by when the owner graded it: an
    # anchor without a date is older than any with one; the order within each index kept)


def is_private(asset):
    """an asset that must never leave this machine: built with rbx.Asset(..., private=True) (its manifest says so), or
    a build script git ignores (a real trademarked design kept out of the repo)"""
    try:
        with open(os.path.join(REPO, "build", "models", f"{asset}.manifest.json"), encoding="utf-8") as fh:
            if json.load(fh).get("private"):
                return True
    except (OSError, ValueError):
        pass
    import subprocess

    script = os.path.join("assets", "models", f"build_{asset}.py")
    try:
        return subprocess.run(["git", "check-ignore", "-q", script], cwd=REPO, capture_output=True,
                              timeout=20).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def pick_anchor(asset, anchors):
    """the ONE anchor a packet shows as a picture: the owner's grade of THIS asset when there is one (the same object
    on the owner's scale: the Glock judged 64 where the owner said 85), else the latest grade (anchors: oldest first,
    as _anchors gives them)"""
    own = [a for a in anchors if a.get("asset") == asset]
    return (own or anchors)[-1:]


def _fit(img, w, h, bg=(24, 24, 26)):
    img = img.convert("RGB")
    s = min(w / img.width, h / img.height)
    img = img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))), Image.LANCZOS)
    tile = Image.new("RGB", (w, h), bg)
    tile.paste(img, ((w - img.width) // 2, (h - img.height) // 2))
    return tile


def _label(tile, text, size=26):
    d = ImageDraw.Draw(tile)
    f = _font(size)
    box = d.textbbox((0, 0), text, font=f)
    d.rectangle((0, 0, box[2] + 20, box[3] + 14), fill=(0, 0, 0))
    d.text((10, 6), text, font=f, fill=(255, 210, 90))
    return tile


def fits_vision(w, h):
    """does a w x h image reach a vision model at its own pixels (not shrunk)?"""
    return w * h <= VISION_MAX_PX and max(w, h) <= VISION_MAX_EDGE


def _row(tiles, bg=(24, 24, 26)):
    """[(tile, ...)] side by side, top-aligned, in one image"""
    out = Image.new("RGB", (sum(t.width for t in tiles), max(t.height for t in tiles)), bg)
    x = 0
    for t in tiles:
        out.paste(t, (x, 0))
        x += t.width
    return out


def _cells(grid, cell_w, cell_h):
    """a sheet of equal cells (row by row) -> its cells; empty (all one colour) cells dropped"""
    out = []
    for r in range(grid.height // cell_h):
        for c in range(grid.width // cell_w):
            cell = grid.crop((c * cell_w, r * cell_h, (c + 1) * cell_w, (r + 1) * cell_h))
            lo, hi = cell.convert("L").getextrema()
            if hi - lo > 8:
                out.append(cell)
    return out


def pack_cells(cells, title):
    """equal cells -> images that each fit a vision model at the cells' own size (as many cells per image as fit,
    row by row), each cell numbered, each image titled "<title> i-j of n" -> [Image]"""
    if not cells:
        return []
    cw, ch = cells[0].size
    bar = 40
    cols = max(1, min(len(cells), VISION_MAX_EDGE // cw))
    rows = max(1, (VISION_MAX_PX // (cols * cw) - bar) // ch)
    while cols > 1 and not fits_vision(cols * cw, rows * ch + bar):
        cols -= 1
    per = cols * max(1, rows)
    out = []
    for k in range(0, len(cells), per):
        chunk = cells[k:k + per]
        n_rows = (len(chunk) + cols - 1) // cols
        img = Image.new("RGB", (cols * cw, n_rows * ch + bar), (24, 24, 26))
        for i, cell in enumerate(chunk):
            tile = _label(cell.convert("RGB").copy(), f"{k + i + 1}", size=20)
            img.paste(tile, ((i % cols) * cw, bar + (i // cols) * ch))
        _label_bar = ImageDraw.Draw(img)
        _label_bar.text((10, 8), f"{title} {k + 1}-{k + len(chunk)} of {len(cells)}", font=_font(24),
                        fill=(255, 210, 90))
        out.append(img)
    return out


def _regions(asset, m=None):
    """refs/<asset>.regions.json (or the build's own map: manifest regions_file) -> list of regions (name, box on the
    reference, parts, questions), or []."""
    path = os.path.join(REPO, (m or {}).get("regions_file") or f"refs/{asset}.regions.json")
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh).get("regions", [])
    except (OSError, ValueError):
        return []


def _region_sheet(asset, m, regions, pdir):
    """region sheets: per region, the REFERENCE crop beside the MODEL close-up (numbered R1..Rn), as many regions to an
    image as fit a vision model unshrunk (VISION_MAX_PX / _EDGE: 1560 px wide, two rows) -> [paths]: regions.png,
    regions_2.png, ..."""
    ref_path = os.path.join(REPO, m.get("reference_image") or "")
    ref = Image.open(ref_path).convert("RGB") if os.path.isfile(ref_path) else None
    renders = m.get("regions") or {}
    tw, th, lab = 385, 292, 34
    cols = 2  # region pairs per row
    width = cols * 2 * tw + (cols - 1) * 20
    rows_per = max(1, VISION_MAX_PX // (width * (th + lab)))
    per = cols * rows_per
    f = _font(22)
    paths = []
    for k in range(0, len(regions), per):
        chunk = regions[k:k + per]
        rows = (len(chunk) + cols - 1) // cols
        out = Image.new("RGB", (width, rows * (th + lab)), (24, 24, 26))
        d = ImageDraw.Draw(out)
        for j, reg in enumerate(chunk):
            i = k + j
            r, c = divmod(j, cols)
            x, y = c * (2 * tw + 20), r * (th + lab)
            d.text((x + 6, y + 6), f"R{i + 1} {reg['name']}: REFERENCE | MODEL", font=f, fill=(255, 210, 90))
            if ref is not None and reg.get("box"):
                out.paste(_fit(ref.crop(tuple(reg["box"])), tw, th), (x, y + lab))
            model = renders.get(reg["name"])
            mp = os.path.join(REPO, model) if model else None
            if mp and os.path.isfile(mp):
                out.paste(_fit(Image.open(mp), tw, th), (x + tw, y + lab))
            else:
                d.text((x + tw + 20, y + lab + th // 2), "MISSING on the model", font=f, fill=(255, 90, 90))
        path = os.path.join(pdir, "regions.png" if k == 0 else f"regions_{k // per + 1}.png")
        out.save(path)
        paths.append(path)
    return paths


def packet(asset, structural=None):
    m = _manifest(asset)
    if m is None:
        return _out("fail", f"judge: {asset} has no build", f"build it first: lune run kit asset {asset}")
    # THE STOP: a judge round costs six images and a fresh context; after a stall another tweak round only measures
    # the judges' noise. A new round needs a STRUCTURAL change named (a new method, a missing part, measured data —
    # not a nudged parameter), and then a panel of 3 judges is asked for, never one
    hist = []
    try:
        with open(os.path.join(REPO, "assets", "models", f"{asset}.judge.json"), encoding="utf-8") as fh:
            hist = json.load(fh).get("history", [])
    except (OSError, ValueError):
        pass
    why = stalled([h["score"] for h in hist], max((h.get("spread") or 0.0) for h in hist) if hist else 0.0)
    if why and not structural:
        return _out("fail", f"judge: {asset} STALLED — {why}; no packet for another tweak round",
                    f"change STRUCTURE (a new method, a missing part, measured data), then: lune run kit judge {asset} "
                    f"--structural \"<what changed in the method>\" (a panel of 3 judges) — or stop and show the owner")
    budget = BUDGET_MIN.get(str(m.get("quality") or m.get("tier") or ""), None)
    spent = ""
    if hist and budget:
        import datetime  # noqa: PLC0415

        try:
            t0 = datetime.datetime.strptime(hist[0]["at"], "%Y-%m-%d %H:%M")
            h = (datetime.datetime.now() - t0).total_seconds() / 3600.0
            if h * 60 > budget:
                spent = f" · {h:.1f} h since its first verdict (budget {budget} min: show the owner)"
        except (KeyError, ValueError):
            pass
    renders = os.path.join(REPO, "build", "renders")
    sheet_path = os.path.join(renders, f"{asset}.png")
    if not os.path.isfile(sheet_path):
        return _out("fail", f"judge: {asset} has no preview sheet", f"rebuild with previews: lune run kit asset {asset}")
    clean = os.path.join(renders, f"{asset}.clean.png")   # (the same sheet before the part names were drawn on it)
    if os.path.isfile(clean) and os.path.getmtime(clean) >= os.path.getmtime(sheet_path) - 60:
        sheet_path = clean
    sheet = Image.open(sheet_path).convert("RGB")
    tw, th = sheet.width // 3, sheet.height // 2  # 3x2 sheet: hero, back, scale / front, side, top
    hero = sheet.crop((0, 0, tw, th))
    back = sheet.crop((tw, 0, 2 * tw, th))
    side = sheet.crop((tw, th, 2 * tw, 2 * th))
    # THE PACKET'S IMAGES — each inside a vision model's limits (VISION_MAX_PX / _EDGE), so the judge sees the renders'
    # own pixels: 1 the reference beside the hero, 2 the side view beside the anchor and the previous build, 3.. the
    # close-ups at their own size (two 640 x 480 views an image)
    TW, TH = 768, 600   # (a 640 x 480 view shown at 1.2x: two side by side, 1536 x 600 = 0.92 MP)
    images = []   # [(Image, what it shows)]
    # THE PRODUCT-LIT VIEWS this build keeps (rbx_judgeviews: Cycles under the product studio — the judge's pictures,
    # the owner's call 2026-10-07): its 3/4 and both sides replace the preview sheet's (honest-lit: a polished slide
    # and a polymer frame read as one matte grey there) when the build has them
    vdir = os.path.join(REPO, "build", "judge", asset, "builds", str(m.get("build_id")))

    def _view(name):
        p_ = os.path.join(vdir, f"{name}.png")
        return Image.open(p_).convert("RGB") if os.path.isfile(p_) else None

    lit = {n_: _view(n_) for n_ in ("three_quarter", "left", "right")}
    if lit["three_quarter"] is not None:
        hero = lit["three_quarter"]
    ref = m.get("reference_image")
    ref_path = os.path.join(REPO, ref) if ref else None
    if ref_path and os.path.isfile(ref_path):
        images.append((_row([_label(_fit(Image.open(ref_path), TW, TH), "REFERENCE"),
                             _label(_fit(hero, TW, TH), "MODEL (hero, Cycles + baked maps)")]),
                       "the REFERENCE beside the MODEL's hero view"))
    else:
        images.append((_row([_label(_fit(hero, TW, TH), "MODEL (hero)"), _label(_fit(back, TW, TH), "MODEL (back 3/4)")]),
                       "the MODEL's hero and back 3/4 views"))
    pdir = os.path.join(REPO, "build", "judge", asset)
    known = [a for a in _anchors() if os.path.isfile(os.path.join(KIT, a.get("image") or ""))]
    anchors = pick_anchor(asset, known)
    extra = [(os.path.join(KIT, a["image"]), f"ANCHOR: owner {a['owner']}/100 ({a['asset']})") for a in anchors]
    prev = _previous(asset, m.get("build_id"))
    if prev:
        extra.append((prev[0], f"PREVIOUS BUILD: judged {prev[1]}/100"))
    if lit["left"] is not None and lit["right"] is not None:
        images.append((_row([_label(_fit(lit["left"], TW, TH), "MODEL (left side, orthographic)"),
                             _label(_fit(lit["right"], TW, TH), "MODEL (right side, orthographic)")]),
                       "the MODEL's left and right sides"))
        side = None
    side_tile = (_label(_fit(side, TW if extra else 2 * TW, TH), "MODEL (side, orthographic)") if side is not None
                 else None)
    if extra:
        stack = Image.new("RGB", (TW, TH), (24, 24, 26))
        eh = TH // len(extra)
        for i, (path, text) in enumerate(extra):
            stack.paste(_label(_fit(Image.open(path), TW, eh), text), (0, i * eh))
        what = " and ".join(t.split(":")[0].lower() for _p, t in extra)
        if side_tile is not None:
            images.append((_row([side_tile, stack]), "the MODEL's side view beside " + what))
        else:
            images.append((stack, what))
    elif side_tile is not None:
        images.append((side_tile, "the MODEL's side view"))
    details = os.path.join(renders, f"{asset}_details.png")
    if os.path.isfile(details):
        d = Image.open(details).convert("RGB")
        cells = _cells(d, d.width // 3, d.height // 2) if d.width % 3 == 0 and d.height % 2 == 0 else [d]
        for img in pack_cells(cells, "MODEL close-ups (own size: judge every mount, joint, letter)"):
            images.append((img, "MODEL close-ups at their own size"))
    for img, _what in images:   # (the layout above keeps every image inside the limits; anything else shrinks HERE,
        if not fits_vision(*img.size):   # where it is seen, not silently in the judge's eyes)
            s = min((VISION_MAX_PX / (img.width * img.height)) ** 0.5, VISION_MAX_EDGE / max(img.size))
            img.thumbnail((int(img.width * s), int(img.height * s)), Image.LANCZOS)
    os.makedirs(pdir, exist_ok=True)
    import glob

    for old in glob.glob(os.path.join(pdir, "sheet_*.png")) + glob.glob(os.path.join(pdir, "regions_*.png")):
        os.remove(old)   # (a packet of an earlier build: more close-ups, more regions)

    for old in glob.glob(os.path.join(pdir, "verdict*.json")):  # verdicts of earlier builds: archived, never mixed in
        try:
            with open(old, encoding="utf-8") as fh:
                stale = json.load(fh).get("build") != m.get("build_id")
        except (OSError, ValueError):
            stale = True
        if stale:
            os.replace(old, os.path.join(pdir, f"old_{os.path.basename(old)[:-5]}_{int(os.path.getmtime(old))}.json"))
    sheet_files = []
    for i, (img, what) in enumerate(images):
        p_ = os.path.join(pdir, "sheet.png" if i == 0 else f"sheet_{i + 1}.png")
        img.save(p_)
        sheet_files.append((p_, what))
    regions = _regions(asset, m)
    region_sheets = _region_sheet(asset, m, regions, pdir) if regions else []
    tier = m.get("tier") or "hero"
    rel = lambda p: os.path.relpath(p, REPO).replace("\\", "/")  # noqa: E731
    crit = "\n".join(f"- `{k}` — **{t}**: {d}" for k, t, d in RUBRIC)
    shown = {a.get("image") for a in anchors}
    listed = known[-6:] + [a for a in anchors if a not in known[-6:]]   # (the tile's own anchor always described)
    anchor_txt = "\n".join(f"- owner {a['owner']}/100 — {a['asset']}"
                           + (" (the ANCHOR tile)" if a.get("image") in shown else "") + f": {a.get('note', '')}"
                           for a in listed) or "- (none yet: the owner has not graded anything)"
    if prev:
        anchor_txt += (f"\n- PREVIOUS BUILD tile: this asset's last judged build, scored {prev[1]} by the judges. Score THIS build on "
                       "its own merits; where it is visibly better or worse than the previous one, your scores must say so.")
    verdict = rel(os.path.join(pdir, "verdict_<n>.json"))
    example = {
        "build": m.get("build_id"),
        "judge": "<model>@<harness>, fresh context",
        "criteria": {k: 0 for k, _, _ in RUBRIC},
        "gaps": [{"criterion": "secondary", "where": "front shroud, left side, between the muzzle and the clamps",
                  "reference": "what the reference does there", "fix": "the concrete change"}],
        "strengths": ["..."],
    }
    if prev:
        example["vs_previous"] = "better | same | worse (this build against the PREVIOUS BUILD tile)"
    if regions:
        example["regions"] = {r["name"]: ["yes|no|unclear"] * len(r.get("questions", [])) for r in regions[:2]}
        example["regions"]["..."] = "one answer per question, in order, for EVERY region"
    region_txt = ""
    if regions:
        lines = []
        for i, r in enumerate(regions):
            lines.append(f"**R{i + 1} {r['name']}**")
            lines += [f"  {j + 1}. {q}" for j, q in enumerate(r.get("questions", []))]
        region_txt = f"""
## Region checklist — the region image(s): {", ".join(f"`{rel(p_)}`" for p_ in region_sheets)}
Each region of the reference sits beside the same region of the model, large enough to see small details. For every
question answer **yes** (the model matches the reference there), **no** (it does not) or **unclear** (cannot tell from
the image) — judge the MODEL tile, using the REFERENCE tile as the truth. "MISSING on the model" = no.
{chr(10).join(lines)}
Every "no" is a gap: list the most damaging ones in `gaps` with the region name in `where`.
"""
    prompt = f"""# Judge: {asset} ({tier}, bar {TIERS.get(tier, 75)}) — build {m.get('build_id')}

You are an independent AAA weapon / prop art director. You did NOT build this model and you gain nothing if it
passes. The builder wants to be finished; your job is the truth. Look at EVERY image of the packet, each once, in
this order (each is small enough to reach you at its own pixels: what is not visible in them is not there):
{chr(10).join(f"{i + 1}. `{rel(p_)}` — {what}" for i, (p_, what) in enumerate(sheet_files))}{chr(10) + chr(10).join(f"{len(sheet_files) + j + 1}. `{rel(p_)}` — the region checklist below" for j, p_ in enumerate(region_sheets)) if region_sheets else ''}

Then score it.

## Score each criterion 0-10 (decimals allowed)
{crit}

Levels (the same for every criterion):
{LEVELS}

## Anchors (the owner's own grades — your scale must agree with them)
{anchor_txt}
If this model is not clearly better than an anchor on a criterion, it does not score higher there.

## Rules
- Judge what you SEE in the images, not what the model is "supposed" to have. Missing in the images = missing.
- Against the reference first (if there is one), then against shipped AAA work.
- A total of 95 means: a player could not tell it from a professional AAA hero asset, and the close-ups hold up.
- List at least 5 gaps (every gap, most damaging first) unless the total is 95+: each with `where` (a region a builder
  can find: part + side + position), what the reference does there, and the concrete `fix`.

{region_txt}
## Write the verdict as JSON to `{verdict}`
```json
{json.dumps(example, indent=2)}
```
(`<n>` = the judge number you were given, or 1 if you are the only judge.) Do not compute a total — the kit sums
the criteria. Several judges may score the same build independently (a panel): the kit takes the median per criterion.
Then the builder runs: `lune run kit judge {asset} --record`
"""
    with open(os.path.join(pdir, "PROMPT.md"), "w", encoding="utf-8") as fh:
        fh.write(prompt)
    structural_path = os.path.join(pdir, "structural.txt")
    if structural:
        with open(structural_path, "w", encoding="utf-8") as fh:
            fh.write(str(structural))
    elif os.path.isfile(structural_path):
        os.remove(structural_path)
    who = ("THREE fresh reviewers, each told its judge number 1-3 (a structural change after a stall is measured by a "
           "panel: one judge moves +-4 on the same build)" if structural else
           "a FRESH reviewer (a subagent, another session or another model — never the builder)")
    return _out(
        "pass",
        f"judge packet for {asset} (build {m.get('build_id')}): {len(sheet_files) + len(region_sheets)} image(s) "
        f"({rel(os.path.join(pdir, 'sheet.png'))} ...) + PROMPT.md"
        + (f" · structural: {structural}" if structural else "") + spent,
        f"hand {rel(os.path.join(pdir, 'PROMPT.md'))} to {who}; it writes {verdict}; then run: "
        f"lune run kit judge {asset} --record",
        packet=rel(pdir), structural=structural,
    )


def _check_verdict(v, m, regions=()):
    """-> (problems, criteria, total, gaps) for one judge's verdict."""
    problems = []
    answers = v.get("regions") or {}
    for r in regions:
        got = answers.get(r["name"])
        want = len(r.get("questions", []))
        if not isinstance(got, list) or len(got) != want or any(str(a).lower() not in ("yes", "no", "unclear") for a in got):
            problems.append(f"region {r['name']}: needs {want} answers, each yes / no / unclear")
    if v.get("build") != m.get("build_id"):
        problems.append(f"verdict is for build {v.get('build')}, the current build is {m.get('build_id')} — judge the current build")
    crit = v.get("criteria") or {}
    for k, _, _ in RUBRIC:
        x = crit.get(k)
        if not isinstance(x, (int, float)) or not 0 <= x <= 10:
            problems.append(f"criterion {k} missing or not 0-10")
    if not str(v.get("judge") or "").strip() or "<model>" in str(v.get("judge")):
        problems.append("say who judged (judge: model@harness, fresh context)")
    total = round(sum(float(crit.get(k, 0)) for k, _, _ in RUBRIC if isinstance(crit.get(k), (int, float))), 1)
    gaps = [g for g in (v.get("gaps") or []) if isinstance(g, dict) and str(g.get("where", "")).strip() and str(g.get("fix", "")).strip()]
    if total < 95 and len(gaps) < 5:
        problems.append(f"{len(gaps)} located gaps (each needs where + fix) — below 95 the judge lists at least 5")
    return problems, crit, total, gaps


def _previous(asset, build):
    """(hero image, score) of the last judged build that is not `build`, or None."""
    try:
        with open(os.path.join(REPO, "assets", "models", f"{asset}.judge.json"), encoding="utf-8") as fh:
            hist = json.load(fh).get("history", [])
    except (OSError, ValueError):
        return None
    for h in reversed(hist):
        img = os.path.join(REPO, "build", "judge", asset, f"judged_{h.get('build')}.png")
        if h.get("build") != build and os.path.isfile(img):
            return img, h.get("score")
    return None


def record(asset, verdict_path=None):
    import glob
    import statistics

    m = _manifest(asset)
    if m is None:
        return _out("fail", f"judge: {asset} has no build", f"lune run kit asset {asset}")
    pdir = os.path.join(REPO, "build", "judge", asset)
    paths = [verdict_path] if verdict_path else sorted(glob.glob(os.path.join(pdir, "verdict*.json")))
    panel, rejected = [], []
    regions = _regions(asset, m)
    for path in paths:
        try:
            with open(path, encoding="utf-8") as fh:
                v = json.load(fh)
        except (OSError, ValueError) as e:
            rejected.append(f"{os.path.basename(path)}: unreadable ({e})")
            continue
        problems, crit_, total_, gaps_ = _check_verdict(v, m, regions)
        if problems:
            rejected.append(f"{os.path.basename(path)}: {problems[0]}")
        else:
            panel.append((v, crit_, total_, gaps_))
    if not panel:
        why = rejected[0] if rejected else f"no verdict*.json in {os.path.relpath(pdir, REPO)}"
        return _out("fail", f"judge: no valid verdict for build {m.get('build_id')} — {why}",
                    f"run the judge(s) on the current packet (lune run kit judge {asset}); " + "; ".join(rejected))
    crit = {k: round(statistics.median(float(c[k]) for _, c, _, _ in panel), 2) for k, _, _ in RUBRIC}
    total = round(sum(crit.values()), 1)
    totals = [t for _, _, t, _ in panel]
    spread = round(max(totals) - min(totals), 1)
    gaps = []
    for i in range(max(len(g) for _, _, _, g in panel)):  # interleave: every judge's worst gap first
        gaps += [g[i] for _, _, _, g in panel if i < len(g)]
    v = {"judge": ", ".join(str(p[0].get("judge")) for p in panel),
         "strengths": [x for p in panel for x in p[0].get("strengths", [])]}
    tier = m.get("tier") or "hero"
    bar = TIERS.get(tier, 75)
    path = os.path.join(REPO, "assets", "models", f"{asset}.judge.json")
    try:
        with open(path, encoding="utf-8") as fh:
            old = json.load(fh)
    except (OSError, ValueError):
        old = {}
    history = old.get("history", [])
    # the region checklist: majority vote per question (unclear abstains; a tie is unclear)
    checklist, yes, no = {}, 0, 0
    for r in regions:
        rows = []
        for j, q in enumerate(r.get("questions", [])):
            votes = [str(p[0]["regions"][r["name"]][j]).lower() for p in panel]
            y_, n_ = votes.count("yes"), votes.count("no")
            ans = "yes" if y_ > n_ else "no" if n_ > y_ else "unclear"
            yes += ans == "yes"
            no += ans == "no"
            rows.append({"q": q, "answer": ans, "votes": votes})
        checklist[r["name"]] = rows
    match = round(100 * yes / max(1, yes + no), 1) if regions else None
    fixed, regressed = [], []
    for name, rows in checklist.items():
        before = {row["q"]: row["answer"] for row in (old.get("checklist") or {}).get(name, [])}
        for row in rows:
            if before.get(row["q"]) == "no" and row["answer"] == "yes":
                fixed.append(f"{name}: {row['q']}")
            if before.get(row["q"]) == "yes" and row["answer"] == "no":
                regressed.append(f"{name}: {row['q']}")
    vs = [str(p[0].get("vs_previous", "")).split()[0].lower() for p in panel if p[0].get("vs_previous")]
    history = [h for h in history if h.get("build") != m.get("build_id")]  # re-recording a build replaces it
    history.append({"build": m.get("build_id"), "score": total, "judges": len(panel), "spread": spread,
                    "totals": totals, "match": match, "vs_previous": vs,
                    "at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")})
    try:   # (the change in METHOD that earned this round after a stall: kit judge --structural)
        with open(os.path.join(REPO, "build", "judge", asset, "structural.txt"), encoding="utf-8") as fh:
            history[-1]["structural"] = fh.read().strip()
    except OSError:
        pass
    sheet = os.path.join(REPO, "build", "renders", f"{asset}.png")
    if os.path.isfile(sheet):  # keep this build's hero: the next packet shows it as PREVIOUS BUILD
        img = Image.open(sheet).convert("RGB")
        img.crop((0, 0, img.width // 3, img.height // 2)).save(os.path.join(pdir, f"judged_{m.get('build_id')}.png"))
    failing = [f"{name}: {row['q']}" for name, rows in checklist.items() for row in rows if row["answer"] == "no"]
    record_ = {"asset": asset, "tier": tier, "bar": bar, "build": m.get("build_id"), "score": total,
               "criteria": crit, "gaps": gaps, "strengths": v.get("strengths", []), "judge": v.get("judge"),
               "panel": {"judges": len(panel), "totals": totals, "spread": spread, "vs_previous": vs},
               "match": match, "checklist": checklist, "failing": failing, "fixed": fixed, "regressed": regressed,
               "history": history[-30:]}
    if old.get("pairwise"):  # (the last pairwise tally — kit judge --tally — stays with the verdict)
        record_["pairwise"] = old["pairwise"]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(record_, fh, indent=2)
    prev = history[-2]["score"] if len(history) > 1 else None
    conf = f", {len(panel)} judges, spread {spread}" if len(panel) > 1 else ", 1 judge (a panel of 3 is steadier)"
    moved = progress([h["score"] for h in history], spread)
    delta = "" if prev is None else (f" ({total - prev:+.1f} vs last verdict" + (
        f": inside the judges' noise (±{max(JUDGE_NOISE, spread / 2):g}), not progress" if moved else "") + ")")
    weakest = sorted(crit, key=lambda k: crit[k])[:3]
    top = gaps[0] if gaps else None
    nxt = (f"fix the judge's gaps, most damaging first — {top['where']}: {top['fix']} (all gaps: assets/models/{asset}.judge.json); "
           f"weakest criteria: {', '.join(f'{k} {crit[k]}' for k in weakest)}") if top else "none — the judge found nothing to fix"
    if regions:
        nxt = (f"reference checklist {match}% ({len(failing)} 'no'"
               + (f", {len(regressed)} REGRESSED: {regressed[0]}" if regressed else "")
               + (f", {len(fixed)} fixed" if fixed else "")
               + f") — first failing: {failing[0] if failing else 'none'}; then: " + nxt)
    if moved == "plateau":
        nxt = (f"PLATEAU — the last 3 verdicts sit within ±{max(JUDGE_NOISE, spread / 2):g}: parameter tweaks are chasing "
               "the judges' noise (the Glock's material rounds). Change STRUCTURE — the shape against the reference "
               "model's sections (kit refs sections), a missing part, a wear story readable at judge scale — or stop "
               "and show the owner; " + nxt)
    if vs and vs.count("worse") > len(vs) / 2:
        nxt = "the panel says this build is WORSE than the previous one — revert the change that caused it first; " + nxt
    return _out("pass" if total >= bar else "fail",
                f"judge: {asset} {total}/100{delta} ({tier} bar {bar}{conf})"
                + (f" · reference checklist {match}%" if match is not None else ""), nxt, score=total, match=match)


# how far two fresh judge panels move on the SAME kind of build: the Glock's material rounds, 2026-10-10 — 59.5, 58.5,
# 58.2, 60.1 for colour / gloss nudges the panels asked for both ways round to round (glossier-darker, then
# satin-lighter). A change inside this is not progress, whichever way it went
JUDGE_NOISE = 1.5


def progress(scores, spread=0.0):
    """the verdicts' scores, oldest first (the newest last) -> what the newest one means: "" (no earlier verdict, or a
    real step), "noise" (within the judges' noise of the BEST of the three before it: 60.1 after 59.5 / 58.5 / 58.2 is
    no step), "plateau" (the last 3 all within it: a loop of parameter tweaks chasing noise)"""
    if len(scores) < 2:
        return ""
    band = max(JUDGE_NOISE, spread / 2.0)
    if len(scores) >= 3 and max(scores[-3:]) - min(scores[-3:]) <= band:
        return "plateau"
    return "noise" if abs(scores[-1] - max(scores[-4:-1])) <= band else ""


def stalled(scores, spread=0.0):
    """the verdicts (oldest first) say the loop has stopped learning: the last 3 sit within the noise (a plateau),
    or the best of the last 3 is no better than the best before them (a skull's 36.5 / 38 / 39 / 35 after a 38 —
    seven builds of tweaks, 2026-10-11) -> the reason, or "" """
    if progress(scores, spread) == "plateau":
        return "the last 3 verdicts sit within the judges' noise"
    band = max(JUDGE_NOISE, spread / 2.0)
    if len(scores) >= 4 and max(scores[-3:]) <= max(scores[:-3]) + band:
        return (f"the best of the last 3 verdicts ({max(scores[-3:]):g}) is no step past the best before them "
                f"({max(scores[:-3]):g})")
    return ""


BUDGET_MIN = {"hero": 60, "aaa": 60, "complex": 30, "prop": 10}   # (the owner's HARD budgets, 2026-10-09)


def anchor(asset, owner, note=""):
    """the graded render's hero view -> an ANCHOR every judge packet shows. Kept in KIT_ANCHORS (the kit home's
    anchors: every project's — kit grade sets it) or this kit's own; each anchor is named by its project (KIT_PROJECT),
    so two projects' crates never overwrite each other, and the index is MERGED, never replaced"""
    import re

    sheet = os.path.join(REPO, "build", "renders", f"{asset}.png")
    if not os.path.isfile(sheet):
        return _out("fail", f"anchor: {asset} has no render", f"lune run kit asset {asset}")
    img = Image.open(sheet).convert("RGB")
    hero = img.crop((0, 0, img.width // 3, img.height // 2))
    folder = os.environ.get("KIT_ANCHORS") or os.path.join(KIT, "anchors")
    project = os.environ.get("KIT_PROJECT") or ""
    private = is_private(asset)
    if private:  # a private asset's render stays HERE: this project's anchors/private, which ignores itself in git
        folder = os.path.join(KIT, "anchors", "private")
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, ".gitignore"), "w", encoding="utf-8", newline=chr(10)) as fh:
            fh.write("# private assets' anchors (judge.anchor): never committed, never copied to another project\n*\n")
    index = os.path.join(folder, "anchors.json")
    if os.path.isfile(index):  # an index it cannot read (a merge conflict, a bad edit) is never overwritten
        try:
            with open(index, encoding="utf-8") as fh:
                if not isinstance(json.load(fh), list):
                    raise ValueError("not a list")
        except (OSError, ValueError):
            return _out("fail", f"anchor: {index} cannot be read as a list of anchors — left as it is (nothing written)",
                        f"repair {index} (git diff / git checkout), then grade again")
    os.makedirs(folder, exist_ok=True)
    tag = re.sub(r"[^A-Za-z0-9_-]+", "_", project).strip("_")
    rel = f"anchors/{'private/' if private else ''}{tag + '-' if tag else ''}{asset}_{int(round(float(owner)))}.png"
    hero.save(os.path.join(folder, os.path.basename(rel)))
    items = [a for a in _anchors(folder, private=False) if a.get("image") != rel]
    items.append({"asset": asset, "project": project or None, "owner": float(owner), "image": rel, "note": note,
                  "at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), **({"private": True} if private else {})})
    with open(os.path.join(folder, "anchors.json"), "w", encoding="utf-8", newline=chr(10)) as fh:
        json.dump(items, fh, indent=2)
    return _out("pass", f"anchor: {asset} kept at owner {owner} ({rel}" + (", PRIVATE: this machine only" if private
                else "") + ")", "every judge packet now shows it")


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) >= 2 and a[0] == "packet":
        st = a[a.index("--structural") + 1] if "--structural" in a[:-1] else None
        sys.exit(packet(a[1], st))
    if len(a) >= 2 and a[0] == "record":
        sys.exit(record(a[1], a[2] if len(a) > 2 else None))
    if len(a) >= 3 and a[0] == "anchor":
        sys.exit(anchor(a[1], a[2], " ".join(a[3:])))
    sys.exit(_out("fail", "judge: usage", "judge.py packet|record|anchor <asset> ..."))
