"""director.py - the VFX CREATIVE DIRECTOR (owner 2026-10-24: "keep outputting more VFX ... original ideas ... I want to
see how creative you can get with making a creative director ... improve the vault ... lessons and learning, so that
pipeline improves by itself"). The ideas are the author's; the director is the discipline and the memory around them:

    lune run kit vfx director learn                 distil the owner's taste from the vault -> kit/knowledge/vault/vfx/director.md
    lune run kit vfx director coverage              which of the pipeline's techniques the effects use, and which they never do
    lune run kit vfx director new <name> --idea "<the concept in one line>"
                                                    a concept brief (assets/effects/briefs/<name>.md) carrying the taste
                                                    profile, the techniques nobody has used yet and the required sections
    lune run kit vfx director check <name>          the brief is a design, not a wish: every section filled, >= 3 timed
                                                    beats, a palette that is its OWN (far from every other brief's),
                                                    >= 3 techniques with one never used before, an impact style, a
                                                    dissipation, what it is NOT
    lune run kit vfx director round <name> [--force] one iteration, no hands: its generator, the taste rules, a HEADLESS
                                                    recording (autorec.py), the gate, the critique sheet
    lune run kit vfx director review <name>         after `kit vfx play <name> --record`: the critique sheet - the gate's
                                                    failures, each beat against the lifecycle sheet, the lessons that apply

An original effect declares "scene": {"original": "<brief name>"} instead of a breakdown set (it has no source scene):
the scene gate then requires its brief and the owner's go-ahead for originals (kit approve vfx originals ...).
The loop that makes it learn: every verdict and lesson lands in the vault; `learn` folds them into the taste profile;
every new brief starts from that profile and from the techniques nobody has tried; `review` turns each recording into
critique that becomes lessons. Prints one JSON line (status / summary / next_action) like every kit tool.
"""
import glob
import json
import math
import os
import re
import sys
import time
from collections import Counter

VAULT = os.path.join("kit", "knowledge", "vault", "vfx")
BRIEFS = os.path.join("assets", "effects", "briefs")
EFFECTS = os.path.join("assets", "effects")
SECTIONS = ["Concept", "Shape language", "Palette", "Beats", "Techniques", "Impact style", "Dissipation", "It is NOT"]
IMPACT_STYLES = ["impact_frames", "impact_frames_slash", "impact_frames_kanada", "impact_frames_silhouette",
                 "impact_frames_flashinvert", "impact_frames_mono", "impact_frames_smash", "impact_frames_void",
                 "impact_frames_shatter", "host frames", "none"]  # host frames: the preset's own impact layers (drawn from ITS shape)
# what `coverage` counts: layer kinds, mesh shapes, technique keys, parts (the pipeline's vocabulary)
TECH_KEYS = ["echo", "bursts", "flicker", "rim", "boil", "haze", "path", "onDeath", "lit", "views", "onMaterial", "sweep",
             "erode", "wobble", "step", "outline", "toon", "kick", "streaks", "aberration", "zoom", "dirt", "vignette",
             "squash", "flipbook", "trail", "curl", "attract", "selective", "flare", "split", "slash"]


def out(status, summary, next_action, **kw):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **kw}))
    return 0 if status == "pass" else 1


def read(p):
    try:
        return open(p, encoding="utf-8").read()
    except OSError:
        return ""


def table_rows(md):
    rows, lines = [], md.splitlines()
    for i, line in enumerate(lines):
        header = i + 1 < len(lines) and re.match(r"^\|\s*:?-", lines[i + 1])  # a table's header sits on its separator
        if line.startswith("|") and not re.match(r"^\|\s*:?-", line) and not header:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 4:
                rows.append(cells)
    return rows


# ------------------------------------------------------------------ learn: the owner's taste, distilled from the vault
def calibration_lines():
    try:
        c = calibrate(quiet=True)
    except Exception as e:  # noqa: BLE001 - a broken calibration must not stop learn; it is reported instead
        return [f"- calibration failed: {e}"]
    lines = [f"- loved: {', '.join(c['loved'])}", f"- rejected: {', '.join(c['rejected'])}"]
    for rid, f in c["fired"].items():
        ev = (c.get("evidence") or {}).get(rid) or []
        blunt = (c.get("too_blunt") or {}).get(rid) or []
        lines.append(f"- {rid}: catches {', '.join(f['rejected']) or '-'}" + (f"; his named fault on {', '.join(ev)}" if ev else "")
                     + (f"; TOO BLUNT on {', '.join(blunt)}" if blunt else "")
                     + (f"; HOLLOW: misses {', '.join(c['hollow'][rid])}" if (c.get("hollow") or {}).get(rid) else ""))
    return lines


def learn():
    golden = table_rows(read(os.path.join(VAULT, "golden.md")))
    grave = table_rows(read(os.path.join(VAULT, "graveyard.md")))
    orders = [ln.strip("- ").strip() for ln in read(os.path.join(VAULT, "orders.md")).splitlines() if ln.startswith("- ")]
    rules = [ln.strip("- ").strip() for ln in read(os.path.join(VAULT, "rules.md")).splitlines() if ln.startswith("- ")]
    lessons = []
    for p in sorted(glob.glob(os.path.join(VAULT, "lessons", "*.md"))):
        body = read(p)
        text = re.sub(r"^---.*?---\s*", "", body, flags=re.S).strip()
        first = next((ln for ln in text.splitlines() if ln.strip() and not ln.startswith("#")), "")
        lessons.append((os.path.basename(p)[:10], first[:260]))
    # the recurring themes across lessons + verdict words: which words keep coming back (what the owner keeps asking for)
    corpus = " ".join(l[1] for l in lessons) + " " + " ".join(" ".join(r) for r in grave + golden)
    themes = {}
    for word, pattern in (("look at the render / frames", r"\blook(ed)? at\b|\brender"), ("real source frames", r"\bframes?\b|\bsource\b"),
                          ("fade / dissipation", r"\bfade|dissipat|breaks? down"), ("scale / size", r"\bscale|colossal|size\b"),
                          ("readability from the game camera", r"\bcamera|\bview"), ("originality", r"\boriginal|re-?skin|own look"),
                          ("volume / 3D meshes", r"\bmesh|volume|3d\b"), ("timing / snap", r"\btiming|snap|hold|hit-?stop"),
                          ("colour / palette", r"\bcolou?r|palette|hue"), ("textures drawn in code", r"\bcode-drawn|in code|procedural")):
        themes[word] = len(re.findall(pattern, corpus, re.I))
    loved = [f"- **{r[0]}** {r[1]} - \"{r[3][:140]}\"" + (f" -> decided by: {r[4][:160]}" if len(r) > 4 and r[4] else "") for r in golden]
    hated = [f"- **{r[0]}** {r[1]} - \"{r[3][:140]}\"" + (f" -> {r[4][:160]}" if len(r) > 4 and r[4] else "") for r in grave]
    lines = ["# The creative director's taste profile (VFX)", "",
             f"Distilled {time.strftime('%Y-%m-%d %H:%M')} by `kit vfx director learn` from golden.md, graveyard.md, orders.md, "
             "rules.md and every lesson - re-run after every verdict / lesson. Every new brief starts from this page.", "",
             "## What the owner LOVED (do more of what decided these)", *(loved or ["- (no golden pieces yet)"]), "",
             "## What the owner REJECTED (never again)", *(hated or ["- (no graveyard yet)"]), "",
             "## Standing orders", *([f"- {o[:220]}" for o in orders[-12:]] or ["- (none)"]), "",
             "## Live rules", *([f"- {r[:220]}" for r in rules[-12:]] or ["- (none)"]), "",
             "## Recurring themes (how often each comes back across lessons + verdicts: the owner's real priorities)",
             *[f"- {k}: {v}" for k, v in sorted(themes.items(), key=lambda kv: -kv[1])], "",
             "## Taste rules (checked on every preset by `kit vfx director lint`; kit/knowledge/vault/vfx/director_rules.json)",
             *[f"- **{r['id']}** ({r.get('piece', '')}): {r['lesson']}" for r in load_rules()], "",
             "## Calibration (every rule on the owner's loved and rejected pieces; a rule may never condemn a loved one)",
             *calibration_lines(), "",
             "## The newest lessons (the brief's checklist)", *[f"- {d}: {t}" for d, t in lessons[-15:]], ""]
    os.makedirs(VAULT, exist_ok=True)
    dest = os.path.join(VAULT, "director.md")
    open(dest, "w", encoding="utf-8", newline="\n").write("\n".join(lines))
    return out("pass", f"director learn: taste profile from {len(golden)} loved, {len(grave)} rejected, {len(lessons)} lessons, "
               f"{len(orders)} orders -> {dest.replace(os.sep, '/')}", "lune run kit vfx director new <name> --idea \"...\"", profile=dest.replace(os.sep, "/"))


# ------------------------------------------------------------------ coverage: the vocabulary used, and never used
def coverage(quiet=False, exclude=None):
    counts = {k: 0 for k in TECH_KEYS}
    parts, kinds, shapes = {}, {}, {}
    # exclude: the brief's OWN effect (review 2026-10-24: once built, its "new" technique stopped counting as new and
    # check failed the brief it had passed)
    files = [p for p in glob.glob(os.path.join(EFFECTS, "*.json")) if not os.path.basename(p).startswith("_")
             and os.path.basename(p)[:-5] != exclude and not os.path.basename(p).startswith(f"{exclude}_")]
    for p in files:
        try:
            d = json.load(open(p, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(d, dict):
            continue
        for u in d.get("use") or []:
            if isinstance(u, dict) and u.get("part"):
                parts[u["part"]] = parts.get(u["part"], 0) + 1
        blob = json.dumps(d)
        for k in TECH_KEYS:
            counts[k] += len(re.findall(r'"%s"\s*:' % re.escape(k), blob))
        for l in d.get("layers") or []:
            if isinstance(l, dict):
                kinds[l.get("kind", "?")] = kinds.get(l.get("kind", "?"), 0) + 1
                if l.get("kind") == "mesh":
                    shapes[l.get("shape", "?")] = shapes.get(l.get("shape", "?"), 0) + 1
    # mesh SHAPES count as vocabulary too (2026-10-24: the new torus was not "new" to check): every shape the runtimes
    # know, at 0 when no effect uses it
    for sh in ("ring", "disc", "tube", "crown", "cone", "sphere", "torus", "dome", "spiral", "arc", "flame", "tongue", "bolt", "spikes", "cards", "corona"):
        shapes.setdefault(sh, 0)
    all_parts = [os.path.basename(p)[:-5] for p in glob.glob(os.path.join(EFFECTS, "parts", "*.json"))]
    unused_parts = sorted(p for p in all_parts if not parts.get(p))
    rare = sorted((k for k in TECH_KEYS if counts[k] <= 2), key=lambda k: counts[k]) + sorted(sh for sh, n in shapes.items() if n <= 2)
    res = {"effects": len(files), "never_or_rarely_used_keys": rare, "unused_parts": unused_parts,
           "keys": counts, "kinds": kinds, "mesh_shapes": shapes, "parts": parts}
    if quiet:
        return res
    return out("pass", f"director coverage: {len(files)} effects; rarely / never used: {', '.join(rare[:12]) or '-'}; parts never used: "
               f"{', '.join(unused_parts[:10]) or '-'}", "build a brief around one of them: lune run kit vfx director new <name> --idea \"...\"", **res)


# ------------------------------------------------------------------ new: a brief that starts from the taste + the unexplored
def new(name, idea):
    if not re.fullmatch(r"[a-z][a-z0-9_]{2,40}", name or ""):
        return out("fail", "director new: needs a snake_case name", "lune run kit vfx director new <name> --idea \"...\"")
    os.makedirs(BRIEFS, exist_ok=True)
    path = os.path.join(BRIEFS, f"{name}.md")
    if os.path.isfile(path):
        return out("fail", f"director new: {path} exists", f"lune run kit vfx director check {name}")
    if not os.path.isfile(os.path.join(VAULT, "director.md")):
        learn()
    cov = coverage(quiet=True)
    taste = read(os.path.join(VAULT, "director.md"))
    loved = re.search(r"## What the owner LOVED.*?\n(.*?)\n## ", taste, re.S)
    hated = re.search(r"## What the owner REJECTED.*?\n(.*?)\n## ", taste, re.S)
    body = [f"# {name} - {idea or '<the concept in one line>'}", "",
            "## Concept", "<what it IS, the feeling, the story beat; why it is not something seen before>", "",
            "## References", "<the REAL frames it is built from (2026-11-10, R-vfx-5: every 8+ piece was built from real frames; the"
            " brief-only originals scored 4-6): real footage of the phenomenon, or an anime scene of its kind - each clip and what"
            " it shows. They become the preset's scene.set: lune run kit vfx breakdown <set> --clip <file>, refs lore, refs"
            " measure, then the owner approves the chart (ONE test frame)>", "",
            "## Shape language", "<the shapes that carry it (angular / organic / radial / layered ...) and why>", "",
            "## Palette", "- primary: [r, g, b]", "- secondary: [r, g, b]", "- accent: [r, g, b]", "",
            "## Beats", "| Beat | Time | What happens | Technique |", "|---|---|---|---|",
            "| anticipation | 0.0-0.4 s | | |", "| release | 0.4-0.5 s | | |", "| peak | 0.5-1.0 s | | |", "| dissipation | 1.0-2.0 s | | |", "",
            "## Techniques", "- <>", "", "## Impact style", f"<one of: {', '.join(IMPACT_STYLES)}>", "",
            "## Dissipation", "<how it BREAKS DOWN (erode, sweep tail, shrink, scatter) - never a plain fade>", "",
            "## It is NOT", "<the look it must not become (the last effect's look, a genre swap, a re-skin)>", "",
            "---", "## The director's notes (generated: read before designing, do not edit)",
            f"- Techniques the effects have rarely / never used: {', '.join(cov['never_or_rarely_used_keys'][:10]) or '-'}",
            f"- Parts never used in an effect: {', '.join(cov['unused_parts'][:10]) or '-'}",
            "- The owner LOVED:", *(["  " + ln for ln in (loved.group(1).strip().splitlines()[:6] if loved else [])]),
            "- The owner REJECTED:", *(["  " + ln for ln in (hated.group(1).strip().splitlines()[:6] if hated else [])]), ""]
    open(path, "w", encoding="utf-8", newline="\n").write("\n".join(body))
    return out("pass", f"director new: brief {path.replace(os.sep, '/')} (fill every section, then check it; an original needs REAL frames too:"
               f" a refs set beside the brief, \"scene\": {{\"original\": \"{name}\", \"set\": \"<refs set>\"}})", f"lune run kit vfx director check {name}",
               brief=path.replace(os.sep, "/"))


def sections(md):
    got, cur = {}, None
    for line in md.splitlines():
        m = re.match(r"^## (.+?)\s*$", line)
        if m:
            cur = m.group(1).strip()
            got[cur] = []
            continue
        if line.startswith("---"):
            cur = None
        if cur:
            got[cur].append(line)
    return {k: "\n".join(v).strip() for k, v in got.items()}


def palette_of(text):
    return [tuple(int(x) for x in m) for m in re.findall(r"\[\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\]", text)]


def pal_distance(a, b):  # the closest colour pairing between two palettes, averaged (0 = identical, 441 = opposite)
    if not a or not b:
        return 441.0
    return sum(min(math.dist(x, y) for y in b) for x in a) / len(a)


# ------------------------------------------------------------------ check: a design, not a wish
def check(name):
    path = os.path.join(BRIEFS, f"{name}.md")
    md = read(path)
    if not md:
        return out("fail", f"director check: no brief {path}", f"lune run kit vfx director new {name} --idea \"...\"")
    s = sections(md)
    problems = []
    for sec in SECTIONS:
        v = s.get(sec, "")
        if not v or "<" in v and ">" in v and len(re.sub(r"<[^>]*>", "", v).strip()) < 10:
            problems.append(f"section '{sec}' is empty or still the placeholder")
    beats = [ln for ln in s.get("Beats", "").splitlines() if re.match(r"^\|[^|]+\|\s*[\d.]+\s*-?\s*[\d.]*\s*s\s*\|\s*[^|\s]", ln)]
    if len(beats) < 3:
        problems.append(f"Beats: {len(beats)} filled timed row(s), needs >= 3 (anticipation, release / peak, dissipation)")
    pal = palette_of(s.get("Palette", ""))
    if len(pal) < 2:
        problems.append("Palette: needs >= 2 [r, g, b] colours")
    nearest, near_name = 441.0, None
    for other in glob.glob(os.path.join(BRIEFS, "*.md")):
        on = os.path.basename(other)[:-3]
        if on == name:
            continue
        d = pal_distance(pal, palette_of(sections(read(other)).get("Palette", "")))
        if d < nearest:
            nearest, near_name = d, on
    if pal and nearest < 40:
        problems.append(f"Palette: {round(nearest)} from {near_name}'s - the same colours again (originality: its OWN palette)")
    techs = [ln for ln in s.get("Techniques", "").splitlines() if ln.strip().startswith("-") and len(ln.strip()) > 3]
    if len(techs) < 3:
        problems.append(f"Techniques: {len(techs)}, needs >= 3")
    cov = coverage(quiet=True, exclude=name)
    fresh = [k for k in cov["never_or_rarely_used_keys"] + cov["unused_parts"] if re.search(r"\b%s\b" % re.escape(k), s.get("Techniques", ""))]
    if not fresh:
        problems.append("Techniques: none of them is new to the effects (use at least one rarely / never used key or part: director coverage)")
    style = s.get("Impact style", "")
    if not any(re.search(r"\b%s\b" % st, style) for st in IMPACT_STYLES):
        problems.append(f"Impact style: name one of {', '.join(IMPACT_STYLES)} (and why)")
    if re.search(r"\bfade(s|d)? out\b|\bjust fades?\b", s.get("Dissipation", ""), re.I):
        problems.append("Dissipation: a plain fade - break it down (erode, a sweep tail, shrink, scatter)")
    if problems:
        return out("fail", f"director check {name}: {len(problems)} problem(s): " + "; ".join(problems), "fill the brief, then check it again", problems=problems)
    return out("pass", f"director check {name}: a design - {len(beats)} beats, {len(pal)} colours ({round(nearest)} from the nearest other brief), "
               f"{len(techs)} techniques ({', '.join(fresh)} new to the effects)", f"build it: the preset declares \"scene\": {{\"original\": \"{name}\"}}",
               fresh=fresh)


# ------------------------------------------------------------------ review: the recording against the brief and the lessons
GENERIC_PUFFS = ("gpu_smoke", "gpu_dust_puff", "gpu_dust_puff2", "gpu_smoke_cel")


def craft_checks(preset, metrics, specs=None):
    """the owner's round-1 verdicts (2026-10-24: nine originals 4-7, "the quality degraded") as WARNINGS on every critique
    sheet - not gates: calibration showed each would condemn a loved piece (moonflower's frames span 0.33, nuke_v2 is
    308 generic puff cards). Returns plain-language lines."""
    out = []
    for view, d in ((metrics or {}).get("views") or {}).items():
        sf = sorted(f["sf"] for f in d.get("frames", []) if f.get("sf") is not None)
        if sf and sf[len(sf) // 2] < 0.35:
            out.append(f"[{view}] the impact frames' subject spans {sf[len(sf) // 2]} of the frame (the loved starblade's: 0.53-0.69) - "
                       "a speck on paper: camera \"subject\" (_frames.py subject_frames), a closer frame camera, or frames: false on what "
                       "crowds it")
    layers = (preset or {}).get("layers", [])
    cards, names = 0, []
    for l in layers:
        lit = l.get("lit") if isinstance(l.get("lit"), dict) else {}
        if lit.get("top") in GENERIC_PUFFS or l.get("texture") in GENERIC_PUFFS:
            cards += (l.get("count") or 0) + (l.get("rate") or 0) * (l.get("for") or 0)
            names.append(l.get("name"))
    if cards > 12:
        out.append(f"{cards:.0f} generic lit puff cards ({', '.join(names[:4])}) - the owner's cotton balls: simulate the event as ONE lit "
                   "flipbook (kit/vfx/gpusim.py surge / stem / swirl)")
    for l in layers:
        tex = l.get("texture") or ((l.get("lit") or {}).get("top") if isinstance(l.get("lit"), dict) else None) or ""
        if l.get("kind") == "sprite" and l.get("count") == 1 and l.get("flipbook") and l.get("orientation") == "FacingCameraWorldUp" and "_gpu" in tex:
            size = max_value(l.get("size", 1)) or 1
            y = (l.get("point") or [0, 0, 0])[1]
            if y - size / 2 < 0.15:
                out.append(f"{l.get('name')}: a standing sim card whose bottom is at y {y - size / 2:.1f} - the ground plane slices it along a "
                           f"straight line (a hard flat base): point y = size / 2 + 0.2 ({size / 2 + 0.2:.1f})")
    plain = [l.get("name") for l in layers if l.get("kind") == "mesh" and l.get("material") in ("SmoothPlastic", "Plastic")
             and not l.get("texture") and not l.get("reflectance") and not l.get("toon")]
    if plain:
        out.append(f"untextured plastic meshes ({', '.join(plain[:4])}) read as clay - a texture, `reflectance` for metal / liquid, or toon")
    # a texture on a shape CLOSED round its u (a ring, a torus, a sphere): fx finish fades every image's borders unless the
    # spec says post.border 0 (or "wrap": true - a beam strip's sides joined) - else a transparent column runs down the mesh at
    # u = 0 (skyfall r2: a straight dark line from the hole across the whole cloud deck)
    spec_of = specs or texture_spec
    seams = []
    for l in layers:
        tex = l.get("texture")
        planar = (l.get("params") or {}).get("planar")  # a planar-projected disc (a magic circle): UV = the plane, no u to close
        shape = l.get("shape") or "ring"  # the player's default shape
        if l.get("kind") == "mesh" and shape in WRAPPED_SHAPES and not planar and isinstance(tex, str) and tex:
            sp = spec_of(tex)
            border = (sp or {}).get("post", {}).get("border", 0.03) if isinstance((sp or {}).get("post"), dict) else 0.03
            if sp is not None and not sp.get("wrap") and (border is None or border > 0):
                seams.append(f"{l.get('name')} ({tex})")
    # frames that re-frame the shot (any camera but "none" - the player's default is a close-up) do not line up with the attack
    # on screen (the owner, 2026-10-25: "an impact frame doesn't line up with the attack itself. So it's very weird")
    reframed = sorted({l.get("name", "?").split(".")[0] for l in layers if l.get("kind") == "impact" and l.get("style") in ("frame", "comic", "anime")
                       and l.get("camera", "closeup") != "none"})
    if reframed:
        out.append(f"re-framed impact frames ({', '.join(reframed[:4])}) - they cut away from the shot on screen; camera \"none\" draws "
                   "the live view so the frame lines up with the attack - or drop them: not every hit needs frames")
    if seams:
        out.append(f"seams: {', '.join(seams[:4])} - a shape closed round its u with a border-faded texture draws a transparent "
                   "line down the mesh: post.border 0 in assets/textures/<key>.json (the texture fades its own ends; \"wrap\" is a beam strip's)")
    return out


# the runtime shapes whose u runs all the way round (u = 0 and u = 1 meet; a bolt's u runs round its tube, Ball / Cylinder
# are three's sphere / cylinder UVs): an arc, a spiral, a tongue, spikes, a corona, cards do not close
WRAPPED_SHAPES = ("ring", "disc", "tube", "crown", "cone", "torus", "sphere", "dome", "rock", "flame", "bolt", "Ball", "Cylinder")


def texture_spec(key):
    try:
        return json.load(open(os.path.join("assets", "textures", f"{key}.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return None


def review(name):
    metrics = os.path.join("build", "vfx", "booth", f"{name}_play.metrics.json")
    try:
        m = json.load(open(metrics, encoding="utf-8"))
    except (OSError, ValueError):
        return out("fail", f"director review: no recording {metrics}", f"lune run kit vfx play {name} --record")
    brief = sections(read(os.path.join(BRIEFS, f"{name}.md")))
    failed = []
    for view, d in (m.get("views") or {}).items():
        for c in d.get("checks", []):
            if not c.get("ok"):
                failed.append(f"- [{view}] **{c['name']}** = {json.dumps(c.get('value'))[:120]} -> {c.get('fix', '')[:200]}")
    # strike_snap diagnosed from the curve (2026-10-24: quenchstrike spent 6 blind rounds on it): what is brightest in
    # the 0.35 s after the hit, and how much the scene drifts in the 0.4 s before it
    for view, d in (m.get("views") or {}).items():
        for c in d.get("checks", []):
            if c.get("name") != "strike_snap" or c.get("ok"):
                continue
            # the gate measures CALM frames: impact-frame windows ([at, at + life + 0.05]) are left out (review 2026-10-24:
            # with them in, the frame's own white-out was the "peak" and the diagnosis went blind)
            flash = [(l.get("at") or 0, (l.get("at") or 0) + (l.get("life") or 0.1) + 0.05) for l in (expanded(name) or {}).get("layers", []) if l.get("kind") == "impact"]
            fr = [f for f in (d.get("frames") or []) if not any(a <= f["t"] <= b for a, b in flash)]
            for item in c.get("value") or []:
                try:
                    h = float(str(item).split(":")[0])
                except ValueError:
                    continue
                pre = [f["mean"] for f in fr if h - 0.4 <= f["t"] <= h - 0.02]
                post = [f for f in fr if h <= f["t"] <= h + 0.35]
                if not pre or not post:
                    continue
                lo, peak = min(pre), max(post, key=lambda f: f["mean"])
                first = max((f for f in post if f["t"] <= h + 0.06), key=lambda f: f["mean"], default=post[0])
                drift = max(pre) - lo
                rise = peak["mean"] - lo
                why = []
                if peak["t"] > h + 0.1 and peak["mean"] > first["mean"] * 1.05:
                    why.append(f"something brighter than the strike arrives at {peak['t']:.2f} s (mean {peak['mean']:.1f} vs {first['mean']:.1f} at the hit): move it past {h + 0.35:.2f} s or dim it")
                if rise > 0 and drift / rise > 0.1:
                    why.append(f"the scene drifts {drift:.1f} into the hit (rise {rise:.1f}, {drift / rise:.0%} > 10 %): flatten what ramps in the 0.4 s before it, or make the strike bigger")
                failed.append(f"- [{view}] strike_snap at {h:.2f} s, read off the curve: " + ("; ".join(why) or "a genuinely slow rise into the hit"))
    _, broken = lint_findings(name)  # the taste rules too: lessons already paid for
    failed += [f"- [taste rule {f['rule']}] {f['problem']} -> {f['lesson']}" for f in broken]
    lessons =[ln for ln in read(os.path.join(VAULT, "director.md")).split("## The newest lessons")[-1].splitlines() if ln.startswith("- ")]
    beats = [ln for ln in brief.get("Beats", "").splitlines() if ln.startswith("|") and "---" not in ln and "Beat" not in ln]
    sheets = sorted(glob.glob(os.path.join("build", "vfx", "booth", f"{name}_play_*.png")))
    crafts = craft_checks(expanded(name), m)
    lines = [f"# Director's review - {name}", "", f"Recording: {metrics.replace(os.sep, '/')}; sheets: " + ", ".join(p.replace(os.sep, '/') for p in sheets), "",
             "## The gate", *(failed or ["- every check passes (a green gate is not quality: judge the sheet)"]), "",
             "## Each beat against the lifecycle sheet (answer: does the sheet show it? what is weak?)", *[f"- {b}" for b in beats], "",
             "## The questions every review answers",
             "- The silhouette at the PEAK: one clear shape? (focal)", "- Anticipation: is there tension BEFORE the release, or does it just start?",
             "- The impact: does the frame show THIS attack's shape? does it hit in a frame?", "- Dissipation: does it break down, or fade?",
             "- Is it its OWN look (the brief's 'It is NOT')?", "- What ONE change would most raise it?", "",
             "## Lessons that apply (from the taste profile)", *lessons[-8:], "",
             "## Craft checks (the owner's round-1 verdicts as warnings, not gates)", *([f"- {c}" for c in crafts] or ["- none"]), ""]
    os.makedirs(os.path.join("build", "vfx", "director"), exist_ok=True)
    dest = os.path.join("build", "vfx", "director", f"{name}.review.md")
    open(dest, "w", encoding="utf-8", newline="\n").write("\n".join(lines))
    return out("pass" if not failed else "warn", f"director review {name}: {len(failed)} gate failure(s); critique sheet {dest.replace(os.sep, '/')}",
               "answer it on the sheets, fix the ONE thing that most raises it, record the lesson (kit lesson vfx ...)", review=dest.replace(os.sep, "/"))


# ------------------------------------------------------------------ lint: the taste rules (lessons a number can check)
RULES = os.path.join(VAULT, "director_rules.json")


def load_rules():
    try:
        return json.load(open(RULES, encoding="utf-8"))["rules"]
    except (OSError, ValueError, KeyError):
        return []


def expanded(name, game=None):
    """The preset as the engine sees it (parts copied in, beats resolved): kit vfx expand prints it. game: "none" = the
    project root's preset whatever game is active (calibrate's loved / rejected sets are the root's presets)"""
    import subprocess
    r = subprocess.run(["lune", "run", "kit", "vfx", "expand", name] + (["--game", game] if game else []), capture_output=True, text=True,
                       encoding="utf-8", shell=os.name == "nt")
    txt = r.stdout[r.stdout.find("{"):]
    try:
        return json.loads(txt[:txt.rfind("}") + 1])
    except ValueError:
        return None


def hero_distance(p):
    views = (p.get("booth") or {}).get("viewDefs") or {}
    # a view may be path-only (katana_moveset's cine): take the first view WITH a pos (review 2026-10-24: it crashed)
    order = [views.get("hero")] + list(views.values())
    v = next((x for x in order if isinstance(x, dict) and isinstance(x.get("pos"), list)), None)
    if not v:
        return 30.0
    return max(math.dist(v["pos"], v.get("look", [0, 0, 0])), 1.0)


def is_keys(v):
    return isinstance(v, list) and v and isinstance(v[0], list) and len(v[0]) == 2 and isinstance(v[0][0], (int, float))


def last_value(v):
    if is_keys(v):
        return last_value(v[-1][1])
    if isinstance(v, dict) and "to" in v:
        return v["to"]
    return v


def max_value(v):
    if is_keys(v):
        return max(max_value(kp[1]) for kp in v)
    if isinstance(v, list) and v and all(isinstance(x, (int, float)) for x in v):
        return max(v)
    return v if isinstance(v, (int, float)) else 0


def colour_of(c, pal):
    if isinstance(c, str):
        return pal.get(c)
    if isinstance(c, list) and len(c) == 3 and all(isinstance(x, (int, float)) for x in c):
        return c
    if is_keys(c):
        return colour_of(c[0][1], pal)
    return None


def lint_swarm_trails(p, rule):
    # hair = trails on particles that MEANDER (a swirl, or a strong curl); ballistic sparks with trails are streaks
    def meanders(l):
        return bool((l.get("attract") or {}).get("swirl")) or (l.get("curl") or {}).get("strength", 0) >= 15
    n = sum(l.get("count", 40) for l in p["layers"] if l.get("kind") == "swarm" and l.get("trail") and meanders(l))
    return [f"{n} meandering swarm particles carry trails (> {rule['max']})"] if n > rule["max"] else []


def lint_swarm_dot_size(p, rule):
    d, found = hero_distance(p), []
    for l in p["layers"]:
        # (calibrated: a swarm WITH trails reads as streaks at any size - nuke_v4's debris, loved at 8.7)
        if l.get("kind") == "swarm" and l.get("count", 40) >= 60 and not l.get("trail"):
            size = max_value(l.get("size", 0.3))
            if size / d < rule["min_ratio"]:
                found.append(f"{l['name']}: dots of {size} studs {round(d)} studs from the hero camera ({size / d:.4f} < {rule['min_ratio']})")
    return found


def lint_mesh_footprint(p, rule):
    d, found = hero_distance(p), []
    for l in p["layers"]:
        params = l.get("params")
        # a PLATE is a wide band (width >= 0.2 of the radius, or several strands); a thin ring rolling out is a travelling
        # wave (resonance's sound rings), not a plate
        # GROUND rings only: a flat (not vertical) arc of >= 270 degrees - a partial arc in the air (seam's 40-degree
        # thread on a 30-stud radius) shows a chord, not its radius (2026-10-24 false positive)
        if l.get("kind") == "mesh" and isinstance(params, dict) and isinstance(params.get("radius"), (int, float))                 and (l.get("shape") or "ring") in ("arc", "ring", "disc") and (params.get("arc") or 360) >= 270 and not params.get("vertical"):
            wide = (params.get("width") or 0) / max(params["radius"], 1e-3) >= rule.get("min_band", 0.2) or (params.get("strands") or 1) > 1
            sc = last_value(l.get("scale", 1))
            sx = max(sc[0], sc[2]) if isinstance(sc, list) and len(sc) == 3 else (sc if isinstance(sc, (int, float)) else 1)
            r = params["radius"] * sx
            # a wide band past ~0.6 of the camera distance is a plate; even a THIN ring past ~0.9 sweeps by the camera as a
            # fat band (resonance round 3)
            if r / d > (rule["max_ratio"] if wide else rule.get("max_ratio_thin", 0.9)):
                found.append(f"{l['name']}: reaches {round(r, 1)} studs, {r / d:.2f} of the hero camera's {round(d)} studs")
    return found


def lint_grey_smoke(p, rule):
    sky = (p.get("booth") or {}).get("sky", "night")
    if sky not in rule["skies"]:
        return []
    found, pal = [], p.get("palette") or {}
    for l in p["layers"]:
        if l.get("kind") == "sprite" and "smoke" in str(l.get("texture", "")) and (l.get("lightEmission") or 0) < 0.2:
            c = colour_of(l.get("color"), pal)
            if c:
                lum = 0.3 * c[0] + 0.59 * c[1] + 0.11 * c[2]
                sat = (max(c) - min(c)) / max(max(c), 1)
                if 110 <= lum <= rule.get("max_lum", 205) and sat < 0.16:
                    found.append(f"{l['name']}: grey smoke {c} (lum {round(lum)}, sat {sat:.2f}) under a {sky} sky")
    return found


def mesh_material(l):
    # the material a mesh layer renders with (VfxStage.luau: a toon mesh is SmoothPlastic whatever it says, else Neon)
    return "SmoothPlastic" if l.get("toon") else (l.get("material") or "Neon")  # (VfxStage: toon wins over material)


def lint_neon_untextured_mesh(p, rule):
    # calibrated 2026-10-24 on the golden set: starblade (9.5) and saiyan_ssj_3d (9.0) carry a few untextured Neon RINGS
    # (<= 10 % of their meshes); the rejected rasengan / all-mesh saiyans are 24-68 % untextured Neon with VOLUMES
    # (sphere, spikes, cone, spiral) - the plastic look is a share of the effect, or a volume, not one accent ring
    meshes = [l for l in p["layers"] if l.get("kind") == "mesh"]
    # (a mesh with no material IS Neon - the engine's default, VfxStage: 2026-11-10 an implicit Neon slipped by)
    bare = [l for l in meshes if mesh_material(l) == "Neon" and not l.get("texture")]
    vols = [l for l in bare if l.get("shape") in rule.get("volumes", ["sphere", "spikes", "cone", "spiral", "flame", "tongue", "tube", "crown", "dome"])]
    share = len(bare) / max(len(meshes), 1)
    found = []
    if share >= rule.get("max_share", 0.2):
        found.append(f"{len(bare)} of {len(meshes)} meshes ({share:.0%}) are untextured Neon")
    found += [f"{l['name']}: an untextured Neon {l.get('shape')} (a volume)" for l in vols]
    return found


def lint_glow_decal_light_ground(p, rule):
    ground = (p.get("booth") or {}).get("ground", "")
    if ground not in rule["grounds"]:
        return []
    found, pal = [], p.get("palette") or {}
    for l in p["layers"]:
        if l.get("kind") == "decal" and (l.get("glow") or 0):
            size = last_value(l.get("size", [0, 0, 0])) if is_keys(l.get("size")) else l.get("size", [0, 0, 0])
            span = max(size[0], size[2]) if isinstance(size, list) and len(size) == 3 else 0
            sizes = [(max(kp[1][0], kp[1][2]) if isinstance(kp[1], list) else kp[1]) for kp in l["size"]] if is_keys(l.get("size")) else [span]
            c = colour_of(l.get("color"), pal) or [255, 255, 255]
            sat = (max(c) - min(c)) / max(max(c), 1)
            if max(sizes) >= rule["min_size"] and sat > 0.35:
                found.append(f"{l['name']}: a glowing {c} decal {round(max(sizes), 1)} studs wide on {ground}")
    return found


def lint_few_big_puffs(p, rule):
    found = []
    for l in p["layers"]:
        # CEL smoke only: a lit, simulated smoke sprite IS a whole volume and may be huge (nuke_v4, 8.7, is ONE 140-stud
        # sprite) - the rule fired on quenchstrike's lit steam and would have condemned a loved piece (2026-10-24)
        tex = str(l.get("texture", ""))
        if l.get("kind") == "sprite" and "cel" in tex and any(w in tex for w in ("smoke", "puff", "dust")) and l.get("count") and not l.get("rate"):
            if l["count"] <= rule["max_count"] and max_value(l.get("size", 1)) >= rule["min_size"]:
                found.append(f"{l['name']}: {l['count']} puffs up to {max_value(l['size'])} studs")
    return found


def lint_lit_puff_swarm(p, rule):
    # the owner 2026-10-24 on quenchstrike: "The Effects like Smoke looks horrible" (27 lit gpu_smoke puffs); on nuke_v3 "the
    # smoke looks bad around" and on nuke_v2 (8) "the smoke around it" (4-6 lit gpu_dust_puff emitters round the mushroom)
    # vs nuke_v4 (8.7): the same mushroom with ONE simulated surge card. A `lit` sheet is lit per CARD (top / left / right /
    # back variants): one card is the whole event's volume, many cards are each lit on their own - lumps (cotton balls,
    # rocks). Unlit sim puffs blend into one mass (starblade's smoke_puff_sim walls, 9.5) and are not asked
    found = []
    for l in p["layers"]:
        if l.get("kind") != "sprite" or not l.get("lit"):
            continue
        rate, count = l.get("rate") or 0, l.get("count") or 0
        if rate > 0 or count > rule.get("max_cards", 2):
            sheet = l["lit"].get("top") if isinstance(l["lit"], dict) else l["lit"]
            found.append(f"{l['name']}: " + (f"{rate}/s" if rate > 0 else f"{count}") + f" lit puff cards of {sheet} (each lit on its own: lumps)")
    return found


def lint_untextured_solid_mesh(p, rule):
    # the owner 2026-10-24 on quicksilver: "Meshs ... very low quality" - its 8 meshes (beads, a crown wall, crown fingers,
    # a jet, ripples) were all untextured SmoothPlastic. untextured-neon-mesh asks Neon (the player's default material);
    # this asks every material that shades as a SOLID. Not asked: Glass (refraction) and ForceField (a fresnel rim) - the
    # engine's own effects; a mirror (reflectance >= 0.3 shows the world); a near-black VOID (gravity_lance's core) - no
    # surface to texture. Calibrated: starblade (9.5), saiyan_ssj_3d (9.0) and nuke_v4 (8.7) carry no untextured solid
    pal = p.get("palette") or {}
    meshes = [l for l in p["layers"] if l.get("kind") == "mesh"]

    def void(l):
        c = colour_of(l.get("color"), pal)
        return c is not None and 0.3 * c[0] + 0.59 * c[1] + 0.11 * c[2] < rule.get("void_lum", 40)

    bare = [l for l in meshes if not l.get("texture") and not l.get("surface")
            and mesh_material(l) not in ("Neon", "Glass", "ForceField")
            and (l.get("reflectance") or 0) < 0.3 and not void(l)]
    vols = [l for l in bare if l.get("shape") in rule.get("volumes", ["sphere", "spikes", "cone", "spiral", "flame", "tongue", "tube", "crown", "dome"])]
    share = len(bare) / max(len(meshes), 1)
    found = []
    if bare and share >= rule.get("max_share", 0.2):
        mats = ", ".join(sorted({mesh_material(l) for l in bare}))
        found.append(f"{len(bare)} of {len(meshes)} meshes ({share:.0%}) are untextured solids ({mats})")
    found += [f"{l['name']}: an untextured {mesh_material(l)} {l.get('shape')} (a volume)" for l in vols]
    return found


def lint_coloured_light_light_ground(p, rule):
    ground = (p.get("booth") or {}).get("ground", "")
    if ground not in rule["grounds"]:
        return []
    found, pal, pts = [], p.get("palette") or {}, p.get("points") or {}
    for l in p["layers"]:
        if l.get("kind") != "light":
            continue
        pt = l.get("point", [0, 0, 0])
        pt = pts.get(pt) if isinstance(pt, str) else pt
        c = colour_of(l.get("color"), pal) or [255, 255, 255]
        sat = (max(c) - min(c)) / max(max(c), 1)
        if isinstance(pt, list) and pt[1] <= rule["max_height"] and max_value(l.get("brightness", 1)) >= rule["min_brightness"] and sat > 0.4:
            found.append(f"{l['name']}: a {c} light of {max_value(l.get('brightness', 1))} at {pt[1]} studs over {ground}")
    return found


def lint_echo_stack(p, rule):
    # the EXPANDED preset has no `echo` key any more: its copies are sibling layers "<name>_echo<k>" (review 2026-10-24:
    # the first version read the authored key and could never fire)
    copies = {}
    for l in p["layers"]:
        m = re.match(r"^(.*)_echo\d+$", str(l.get("name", "")))
        if m and l.get("kind") == "mesh" and l.get("shape") == "arc" and l.get("material") == "Neon":
            copies[m.group(1)] = copies.get(m.group(1), 0) + 1
    return [f"{n}: a Neon ring with {c} echoes" for n, c in copies.items() if c > rule["max_copies"]]


def lint_neon_band_light_ground(p, rule):
    ground = (p.get("booth") or {}).get("ground", "")
    if ground not in rule["grounds"]:
        return []
    found, pal = [], p.get("palette") or {}
    for l in p["layers"]:
        params = l.get("params") if isinstance(l.get("params"), dict) else {}
        if l.get("kind") == "mesh" and l.get("shape") == "arc" and l.get("material") == "Neon" and params.get("radius"):
            band = (params.get("width") or 0) / params["radius"]
            c = colour_of(l.get("color"), pal) or [255, 255, 255]
            sat = (max(c) - min(c)) / max(max(c), 1)
            if (band >= rule["min_band"] or (params.get("strands") or 1) > 1) and sat > 0.4:
                found.append(f"{l['name']}: a {c} Neon band ({band:.2f} of its radius) on {ground}")
    return found


def lint_strong_rim_small(p, rule):
    # rules read the EXPANDED preset: a `rim` is already its own ForceField shell layer ("<name>_rim") by then
    found = []
    for l in p["layers"]:
        if l.get("kind") == "mesh" and l.get("material") == "ForceField":
            tr = l.get("transparency", 0.35)
            tr = min(kp[1] for kp in tr) if is_keys(tr) else tr
            sc = max_value(l["scale"].get("to", 1)) if isinstance(l.get("scale"), dict) else max_value(l.get("scale", 1))
            pr = l.get("params") or {}
            dim = pr.get("radius") or pr.get("radiusBottom") or pr.get("outer") or pr.get("height") or 1  # the shape's own size (unit = 1)
            sc = sc * dim if sc else sc  # studs, not the multiplier (review 2026-10-24)
            if isinstance(tr, (int, float)) and tr < rule["min_transparency"] and sc and sc < rule["max_size"]:
                found.append(f"{l['name']}: a rim shell at {tr} on a {round(sc, 2)}-stud mesh")
    return found


def value_at(v, u):
    if is_keys(v):
        for a, b in zip(v, v[1:]):
            if u <= b[0]:
                k = (u - a[0]) / (b[0] - a[0]) if b[0] > a[0] else 0
                av, bv = a[1], b[1]
                if isinstance(av, list) != isinstance(bv, list):  # a number beside a vector key: the number on every axis
                    av, bv = (av if isinstance(av, list) else [av] * 3), (bv if isinstance(bv, list) else [bv] * 3)
                if isinstance(av, list):
                    return [x + (y - x) * k for x, y in zip(av, bv)]
                return av + (bv - av) * k
        return v[-1][1]
    if isinstance(v, dict) and "to" in v:  # an eased curve: its end (good enough for "is it grown")
        return v["to"]
    return v


def lint_frames_drawable(p, rule):
    hits = [h.get("at") for h in (p.get("hitstop") or []) if isinstance(h, dict)]
    frames = [l for l in p["layers"] if l.get("kind") == "impact" and l.get("style") in ("frame", "comic", "anime")]
    found = []
    for h in hits:
        here = [l for l in frames if abs((l.get("at") or 0) - h) <= 0.12]
        if not here:
            continue
        # frames that PAINT their own elements (a Kanada flare, a star, wedges, bolts, a slash stroke) need no scene shapes
        # (noctiluca's Kanada frames, 2026-10-24); draw.crack does not count - it drew nothing on its own (hoarfrost)
        if any(any((l.get("draw") or {}).get(k) for k in ("flare", "star", "wedge", "bolts", "slash")) for l in here):
            continue
        ok = []
        # draw.semantic (on unless false) takes EVERY mesh layer out of the frames' energy pass - only an aimed tube /
        # cone comes back, as a wedge (player.js frame pass: `l.native` is any mesh's bounding box). A flame shell, ring
        # or torus is erased from semantic frames (firewhirl r1-r2: the column vanished, the embers drew a starburst)
        semantic = any((l.get("draw") or {}).get("semantic") not in (False, 0) for l in here)
        wedges = any((l.get("draw") or {}).get("wedge", 1) for l in here)  # the player's frameDraw: wedge defaults to 1

        def erased(m):  # a mesh the semantic frame pass drops from the energy pass and draws no other way
            if m.get("shape") in ("tube", "cone") and m.get("aim") is not None and wedges:
                return False  # an aimed tube / cone comes back as a wedge from its axis (frameData)
            if m.get("shape") == "Block" and (m.get("material") or "Neon") not in ("Neon", "ForceField"):
                return False  # a lit Block is a Lambert box: the ink pass (sil), never the energy pass
            return True
        for l in p["layers"]:
            if l.get("frames") is False:
                continue  # kept out of the impact frames: draws nothing in them (review 2026-10-25)
            at, k = l.get("at") or 0, l.get("kind")
            life = l.get("life") or max_value(l.get("lifetime", 1)) or 1
            if not (at - 0.01 <= h + 0.06 and h <= at + life + (l.get("for") or 0)):
                continue  # not alive across the frames' first moments
            if k in ("debris", "swarm"):
                ok.append(l["name"])
            elif k == "mesh" and semantic and erased(l):
                continue
            elif k == "mesh":
                sc = value_at(l.get("scale", 1), max(0.0, min(1.0, (h + 0.06 - at) / max(life, 1e-3))))
                grown = (min(sc) if isinstance(sc, list) else sc) > 0.2
                lit = l.get("material") in (None, "SmoothPlastic", "Plastic", "Slate", "Rock", "Metal", "Neon")
                if grown and lit:
                    ok.append(l["name"])
            elif k == "sprite" and (l.get("lightEmission") if l.get("lightEmission") is not None else 1) >= 0.5 and max_value(l.get("size", 1)) >= 2:
                ok.append(l["name"])  # (specks do not hold a frame: hoarfrost's empty frames showed only its 0.35-stud diamond dust)
            elif k == "beam" and max_value(l.get("width", 1)) >= 0.5:
                ok.append(l["name"])
        if not ok:
            found.append(f"frames at {h:.2f} s: nothing the frame pass can draw is alive and grown there (no debris / swarm / lit grown mesh / bright layer)")
    return found


def lint_cut_frames_arc(p, rule):
    found = []
    for h in [x.get("at") for x in (p.get("hitstop") or []) if isinstance(x, dict)]:
        cut = [l for l in p["layers"] if l.get("kind") == "impact" and abs((l.get("at") or 0) - h) <= 0.12
               and ((l.get("draw") or {}).get("slash") or (l.get("draw") or {}).get("split") or l.get("lines") == "cut")]
        if not cut:
            continue
        ok = False
        for l in p["layers"]:
            if l.get("kind") != "mesh" or l.get("shape") != "arc":
                continue
            at, life = l.get("at") or 0, l.get("life") or 1
            if not (at <= h + 0.02 and h <= at + life):
                continue
            sw = l.get("sweep") or {}
            u = max(0.0, min(1.0, (h - at) / max(life, 1e-3)))  # AT the hit: the frames render there, not after
            head = value_at(sw["head"], u) if is_keys(sw.get("head")) else (sw.get("head") if sw.get("head") is not None else 1)
            tail = value_at(sw["tail"], u) if is_keys(sw.get("tail")) else (sw.get("tail") or 0)
            if head - tail >= rule["min_head"]:  # the DRAWN window (review 2026-10-24: an arc already erased counted)
                ok = True
        if not ok:
            found.append(f"slash frames at {h:.2f} s: no arc is alive and drawn there (a sweep from zero has no centreline)")
    return found


LINTS = {"cut_frames_arc": lint_cut_frames_arc, "frames_drawable": lint_frames_drawable, "strong_rim_small": lint_strong_rim_small, "echo_stack": lint_echo_stack, "neon_band_light_ground": lint_neon_band_light_ground, "coloured_light_light_ground": lint_coloured_light_light_ground, "glow_decal_light_ground": lint_glow_decal_light_ground, "few_big_puffs": lint_few_big_puffs, "swarm_trails": lint_swarm_trails, "swarm_dot_size": lint_swarm_dot_size, "mesh_footprint": lint_mesh_footprint,
         "grey_smoke": lint_grey_smoke, "neon_untextured_mesh": lint_neon_untextured_mesh,
         "lit_puff_swarm": lint_lit_puff_swarm, "untextured_solid_mesh": lint_untextured_solid_mesh}


def lint_thin_stack(p, rule):
    # the owner 2026-11-11 on flame_arc (REDO: "Does not look high quality ... genuine dookie") and 2026-11-10 on
    # flame_arc_keybeat (REDO): a whole technique built from a few kinds of layer, mostly flat sprites. Measured on
    # every loved piece (2026-11-11): 7-13 kinds, at most 67 % sprites (sumi_seal); starblade r6 (9.5) is 148 layers of 13
    # kinds - mesh shells, beams, lights, screen + fov + shake, decals, debris, a trail, a glow, sound. Asked only of a piece
    # built through the route (it declares a scene: set or original) - a muzzle flash is not a technique
    if not isinstance(p.get("scene"), dict):
        return []
    kinds = Counter(l.get("kind", "?") for l in p["layers"] if isinstance(l, dict))
    n = sum(kinds.values())
    if not n:
        return []
    share = kinds.get("sprite", 0) / n
    thin = len(kinds) <= rule.get("max_kinds", 5)
    flat = share >= rule.get("max_sprite_share", 0.75)
    if not (thin or flat):
        return []
    return [f"a thin stack: {n} layers of {len(kinds)} kinds ({', '.join(f'{k} {c}' for k, c in kinds.most_common())}), "
            f"{share:.0%} flat sprites - his loved pieces use 7-13 kinds and at most 67 % sprites"]


LINTS["thin_stack"] = lint_thin_stack


def lint_findings(name):
    # a .json path (selftest fixtures, ad-hoc files): load directly — no expand needed, no parts/beats
    if name.endswith(".json") and os.path.isfile(name):
        try:
            p = json.load(open(name, encoding="utf-8"))
        except (OSError, ValueError):
            return None, []
    else:
        p = expanded(name)
    if p is None:
        return None, []
    if p.get("version") != 3 or not isinstance(p.get("layers"), list):  # legacy presets (review: KeyError 'layers')
        return p, []
    found = []
    for rule in load_rules():
        fn = LINTS.get(rule.get("type"))
        if fn is None:
            found.append({"rule": rule.get("id"), "problem": f"unknown rule type {rule.get('type')}", "lesson": ""})
            continue
        for problem in fn(p, rule):
            found.append({"rule": rule["id"], "problem": problem, "lesson": rule["lesson"], "piece": rule.get("piece")})
    return p, found


def lint(name):
    p, found = lint_findings(name)
    if p is None:
        return out("fail", f"director lint: cannot expand {name}", f"lune run kit vfx expand {name}")
    if not found:
        return out("pass", f"director lint {name}: all {len(load_rules())} taste rules hold", f"lune run kit vfx play {name} --record")
    return out("warn", f"director lint {name}: {len(found)} taste rule(s) broken: " + "; ".join(f"[{f['rule']}] {f['problem']}" for f in found),
               "each one is a lesson already paid for - fix it before recording", findings=found)


# ------------------------------------------------------------------ calibrate: a rule must never condemn a loved piece
def taste_sets():
    """loved = golden.md rows + verdicts scored >= 7 + pieces the owner praised in words (director_rules.json
    "praised"); rejected = graveyard.md rows + verdicts scored <= 3 - only those that exist as presets."""
    exists = lambda n: os.path.isfile(os.path.join(EFFECTS, f"{n}.json"))
    first = lambda cell: re.split(r"[\s(]", cell.strip("*` "))[0]
    loved = {first(r[0]) for r in table_rows(read(os.path.join(VAULT, "golden.md")))}
    rejected = {first(r[0]) for r in table_rows(read(os.path.join(VAULT, "graveyard.md")))}
    try:
        for name, lst in json.load(open(os.path.join("library", "vfx", "verdicts.json"), encoding="utf-8")).items():
            for v in (lst if isinstance(lst, list) else [lst]):
                sc = v.get("score") if isinstance(v, dict) else None
                if isinstance(sc, (int, float)):
                    (loved if sc >= 7 else rejected if sc <= 3 else set()).add(name)
    except (OSError, ValueError):
        pass
    try:
        loved |= set(json.load(open(RULES, encoding="utf-8")).get("praised", {}))
    except (OSError, ValueError):
        pass
    return sorted(n for n in loved if exists(n)), sorted(n for n in rejected - loved if exists(n))


def calibrate(quiet=False, evidence_only=False):
    loved, rejected = taste_sets()
    rules = load_rules()
    fired = {r["id"]: {"loved": [], "rejected": []} for r in rules}
    skipped = []  # (review 2026-11-10: with a game active every expand missed the root's presets and calibrate "passed" on nothing)
    for group, names in (() if evidence_only else (("loved", loved), ("rejected", rejected))):
        for n in names:
            p = expanded(n, game="none")
            if p is None:
                skipped.append(n)
                continue
            for rule in rules:
                fn = LINTS.get(rule.get("type"))
                if fn and fn(p, rule):
                    fired[rule["id"]][group].append(n)
    # EVIDENCE (2026-11-10): a rule born from the owner's words names the pieces he said them about and the version he
    # JUDGED (a selftest fixture, never the reworked preset: reworks erase the evidence). It must fire on each - a rule
    # that misses its own evidence is HOLLOW (few-giant-puffs was narrowed on 2026-10-24 until it no longer fired on
    # quenchstrike, the piece he called "smoke looks horrible"). A loved piece he named THIS fault on (nuke_v2, 8: "the
    # smoke around it") is the rule working, not a blunt rule; and the 4-6 pieces count - <= 3 alone hid every round-1 fault
    hollow, named = {}, {}
    for rule in rules:
        fn = LINTS.get(rule.get("type"))
        for ev in rule.get("evidence") or []:
            pieces = named.setdefault(rule["id"], set())
            pieces.add(ev.get("piece"))
            try:
                p = json.load(open(ev.get("judged", ""), encoding="utf-8"))
            except (OSError, ValueError):
                p = None
            if fn is None or p is None or not fn(p, rule):
                hollow.setdefault(rule["id"], []).append(ev.get("piece"))
    blunt = {k: [n for n in v["loved"] if n not in named.get(k, set())] for k, v in fired.items()}
    blunt = {k: v for k, v in blunt.items() if v}
    res = {"loved": loved, "rejected": rejected, "fired": fired, "too_blunt": blunt, "hollow": hollow,
           "evidence": {k: sorted(v) for k, v in named.items()}, "skipped": skipped}
    if quiet:
        return res
    if evidence_only:  # kit selftest: every rule with evidence must catch it (a rule that misses its own evidence fails)
        n_ev = sum(len(v) for v in named.values())
        return out("fail" if hollow else "pass",
                   f"director calibrate --evidence-only: {len(named)} rule(s), {n_ev} judged piece(s) as evidence; "
                   + ("HOLLOW (miss their own evidence): " + "; ".join(f"{k} -> {', '.join(v)}" for k, v in hollow.items()) if hollow else "every rule catches its own evidence"),
                   "a hollow rule misses the very piece it was made from: fix the rule, never the evidence" if hollow else "none", **res)
    caught = sorted({n for v in fired.values() for n in v["rejected"]})
    bad = blunt or hollow or skipped
    return out("pass" if not bad else "warn",
               f"director calibrate: {len(rules)} rules on {len(loved)} loved + {len(rejected)} rejected pieces; "
               + (f"TOO BLUNT (fire on loved pieces): " + "; ".join(f"{k} -> {', '.join(v)}" for k, v in blunt.items()) if blunt else "no rule condemns a loved piece")
               + (f"; HOLLOW (miss their own evidence): " + "; ".join(f"{k} -> {', '.join(v)}" for k, v in hollow.items()) if hollow else "")
               + f"; rejected pieces caught: {', '.join(caught) or '-'}"
               + (f"; NOT CHECKED (no preset to expand): {', '.join(skipped)}" if skipped else ""),
               ("narrow every too-blunt rule until it holds on the loved set (evidence beats the rule)" if blunt else "")
               + (("; " if blunt else "") + "a hollow rule misses the very piece it was made from: fix the rule, never the evidence" if hollow else "")
               or "lune run kit vfx director learn", **res)


# ------------------------------------------------------------------ bisect: WHICH layer causes a gate failure
def check_fails(name, check, view):
    try:
        m = json.load(open(os.path.join("build", "vfx", "booth", f"{name}_play.metrics.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return None
    d = (m.get("views") or {}).get(view) or {}
    for c in d.get("checks", []):
        if c.get("name") == check:
            return not c.get("ok")
    return None


def bisect(name, check, view="hero"):
    """Remove half of the candidate layers in a probe copy, record it headless, keep the half the failure follows -
    log2(layers) recordings (~30 s each) instead of guessing (2026-10-24: quenchstrike's strike_snap took 6 blind
    rounds). Probes are `_bisect_<name>` presets (skipped by the gate) and are cleaned out of the library afterwards."""
    import shutil
    import subprocess
    base = expanded(name)
    if base is None:
        return out("fail", f"director bisect: cannot expand {name}", f"lune run kit vfx expand {name}")
    probe = f"_bisect_{name}"
    keep_kinds = {"impact", "shake", "fov", "sound", "world"}  # the frame / feel layers are not suspects (they shape the measure)
    cand = [l["name"] for l in base["layers"] if l.get("kind") not in keep_kinds]
    fixed = [l for l in base["layers"] if l.get("kind") in keep_kinds]
    steps, t0 = [], time.time()

    def run_without(removed):
        pre = dict(base)
        pre["layers"] = fixed + [l for l in base["layers"] if l["name"] in cand and l["name"] not in removed]
        pre.pop("use", None)
        json.dump(pre, open(os.path.join(EFFECTS, f"{probe}.json"), "w", encoding="utf-8", newline="\n"), indent=1)
        r = subprocess.run([sys.executable, "-I", os.path.join("kit", "vfx", "autorec.py"), probe, "--views", view],
                           capture_output=True, text=True, encoding="utf-8")
        return check_fails(probe, check, view)

    try:
        if run_without(set()) is not True:
            return out("fail", f"director bisect {name}: {check} does not fail in the {view} view of the probe - nothing to find",
                       f"lune run kit vfx director round {name}")
        suspects = list(cand)
        while len(suspects) > 1:
            half = set(suspects[: len(suspects) // 2])
            fails = run_without(half)
            steps.append({"removed": sorted(half), "still_fails": fails})
            if fails is False:
                suspects = [s for s in suspects if s in half]  # removing that half cured it: the culprit is in it
            elif fails is True:
                suspects = [s for s in suspects if s not in half]
            else:
                break
        cured = run_without(set(suspects)) is False if suspects else False
    finally:
        os.remove(os.path.join(EFFECTS, f"{probe}.json")) if os.path.isfile(os.path.join(EFFECTS, f"{probe}.json")) else None
        shutil.rmtree(os.path.join("library", "vfx", "effects", probe), ignore_errors=True)
        for f in glob.glob(os.path.join("build", "vfx", "booth", f"{probe}_*")) + glob.glob(os.path.join("build", "vfx", "play", f"{probe}*")):
            os.remove(f) if os.path.isfile(f) else shutil.rmtree(f, ignore_errors=True)
    verdict = (f"{suspects[0]} alone causes it (removing it cures {check})" if len(suspects) == 1 and cured else
               f"no single layer: the narrowest set is {', '.join(suspects)}" + (" (removing them cures it)" if cured else " (several layers together)"))
    return out("pass", f"director bisect {name} {check} [{view}]: {verdict}; {len(steps) + 2} recordings in {round(time.time() - t0)} s",
               "change THAT layer (read its curve), then round again", suspects=suspects, steps=steps)


# ------------------------------------------------------------------ round: one whole iteration, no hands
def round_(name, force=False):
    """generator -> taste rules -> a HEADLESS recording (autorec.py: the player in a local headless browser) -> the
    gate's checks -> the critique sheet. One command per iteration of an original (2026-10-24: rounds used to need the
    agent to drive a browser pane by hand, and a recording started before the server was up silently never ran)."""
    import subprocess
    t0 = time.time()
    gen = os.path.join(EFFECTS, "generators", f"{name}.py")
    if os.path.isfile(gen):
        r = subprocess.run([sys.executable, "-I", gen], capture_output=True, text=True, encoding="utf-8")
        if r.returncode != 0:
            return out("fail", f"director round {name}: the generator failed: {(r.stderr or r.stdout).strip()[-300:]}", f"fix {gen}")
    # the gate's own validator on this one preset first (a cut-off / bad key used to surface only after a whole gate run)
    v = subprocess.run(["lune", "run", "kit", "vfx", "expand", name, "--check"], capture_output=True, text=True, encoding="utf-8", shell=os.name == "nt")
    errs = [ln for ln in (v.stderr or "").splitlines() if ln.strip()]
    if v.returncode != 0 or errs:
        return out("fail", f"director round {name}: {len(errs)} validator error(s): " + "; ".join(errs[:4]), "fix the preset (its generator), then round again", errors=errs)
    p, broken = lint_findings(name)
    if p is None:
        return out("fail", f"director round {name}: cannot expand it", f"lune run kit vfx expand {name}")
    if broken and not force:
        return out("fail", f"director round {name}: {len(broken)} taste rule(s) broken (lessons already paid for): "
                   + "; ".join(f"[{f['rule']}] {f['problem']}" for f in broken), "fix them, or --force to record anyway", findings=broken)
    views = ",".join((p.get("booth") or {}).get("views") or ["hero", "cine", "combat"])
    r = subprocess.run([sys.executable, "-I", os.path.join("kit", "vfx", "autorec.py"), name, "--views", views],
                       capture_output=True, text=True, encoding="utf-8")
    line = next((ln for ln in reversed(r.stdout.splitlines()) if ln.startswith("{")), "")
    try:
        rec = json.loads(line)
    except ValueError:
        rec = {"status": "fail", "summary": (r.stdout + r.stderr).strip()[-300:]}
    if rec.get("status") != "pass":
        return out("fail", f"director round {name}: the recording failed: {rec.get('summary', '')[:300]}", "read the autorec output")
    try:
        m = json.load(open(os.path.join("build", "vfx", "booth", f"{name}_play.metrics.json"), encoding="utf-8"))
    except (OSError, ValueError):
        m = {}
    failed = sorted({f"{c['name']}" for d in (m.get("views") or {}).values() for c in d.get("checks", []) if not c.get("ok")})
    review(name)
    sheet = os.path.join("build", "vfx", "booth", f"{name}_play_{views.split(',')[0]}.png").replace(os.sep, "/")
    return out("pass" if not failed else "warn",
               f"director round {name}: recorded {views} in {round(time.time() - t0)} s; gate {'green' if not failed else 'fails: ' + ', '.join(failed)}; "
               f"taste rules {'hold' if not broken else str(len(broken)) + ' broken (forced)'}",
               f"LOOK at {sheet} (the lifecycle sheet), answer build/vfx/director/{name}.review.md, change ONE thing, round again",
               sheet=sheet, failed=failed)


def main(argv):
    if not argv:
        return out("fail", "director: learn | coverage | new <name> --idea \"...\" | check <name> | lint <name> | calibrate | bisect <name> <check> [--view v] | round <name> [--force] | review <name>", "lune run kit vfx director learn")
    cmd, rest = argv[0], argv[1:]
    if cmd == "learn":
        return learn()
    if cmd == "coverage":
        return coverage()
    if cmd == "new":
        idea = rest[rest.index("--idea") + 1] if "--idea" in rest and rest.index("--idea") + 1 < len(rest) else ""
        return new(rest[0] if rest else "", idea)
    if cmd == "check":
        return check(rest[0] if rest else "")
    if cmd == "lint":
        return lint(rest[0] if rest else "")
    if cmd == "calibrate":
        return calibrate(evidence_only="--evidence-only" in rest)
    if cmd == "bisect":
        view = rest[rest.index("--view") + 1] if "--view" in rest and rest.index("--view") + 1 < len(rest) else "hero"
        return bisect(rest[0] if rest else "", rest[1] if len(rest) > 1 else "strike_snap", view)
    if cmd == "round":
        return round_(rest[0] if rest else "", "--force" in rest)
    if cmd == "review":
        return review(rest[0] if rest else "")
    return out("fail", f"director: unknown command {cmd}", "lune run kit vfx director learn")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
