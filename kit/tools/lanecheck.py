"""lanecheck.py — before a build in every content lane but 3D (3D: kit/tools/plan.py --prebuild): the piece's time budget
and its route. The owner, 2026-11-10, after the car rim's three fixes (card bv3n) went to 3D only: "keep going on the
3D ... but don't forget about the other ones" and, on the budgets, "Yes, same budgets" (card b6m2).

  python kit/tools/lanecheck.py prebuild <lane> <name> --dir <the piece's folder> [--tier T] [--no-clock]
  python kit/tools/lanecheck.py prebuild-all <lane> --root <the project: '' or games/<G>/>
  python kit/tools/lanecheck.py route <lane> <name> --dir <the piece's folder>
  python kit/tools/lanecheck.py piece anim <clip>
  python kit/tools/lanecheck.py extend <lane> <name> <minutes> "<the owner's words>" --dir <folder>
  python kit/tools/lanecheck.py restart <lane> <name> "<the owner's words>" --dir <folder> [--tier T]

THE CLOCK: 3D's tiers for every lane - 10 minutes a simple piece, 30 a complex one, 60 a hero (an aaa too) - from the
piece's first build; the tier is the one the attempt started on; past it no CHANGE to the piece builds (the piece as it
was may still be built, played, looked at) until the owner's words (`lune run kit clock <lane> <name> --extend
<minutes> "<his words>"`, or `--restart "<his words>"`: a new attempt). Kept at <project>/assets/clocks/<lane>/<name>.clock.json.
THE ROUTE: the ways a piece is made, read from its own files - vfx: the techniques its layers use; anim: its dossier's
builder and the kinds of source it builds from; ui: its pieces' routes and its identity pack; sfx: recorded / synth;
world: terrain / meshes. The lessons sheet's record (board/answers.json) keeps the route its answers were written for;
a build whose route GAINED a way refuses until `lune run kit answer <lane> <name> --reroute` and every lesson is
answered again for it. A sheet recorded before routes were kept takes the route it first builds on. A rebuild of every
piece (prebuild-all) starts no clock: it refuses only a piece past its budget and changed, or whose route gained a way."""

import fnmatch
import hashlib
import json
import math
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import plan as PL  # noqa: E402  (the budgets, the owner's minutes rule and the open cards: one place for all lanes)

LANES = ("vfx", "ui", "anim", "sfx", "world")
LANE_DIR = {"vfx": "assets/effects", "ui": "assets/ui", "anim": "assets/animations/dossiers",
            "sfx": "assets/sounds", "world": "assets/worlds"}
TIERS = {"simple": 10, "prop": 10, "complex": 30, "hero": 60, "aaa": 60}
# a piece that names no tier: an effect, a clip and a world are complex work; a single sound and a screen simple
DEFAULT_TIER = {"vfx": "complex", "anim": "complex", "world": "complex", "ui": "simple", "sfx": "simple"}

# vfx: a layer's kind -> the technique family it belongs to (a new FAMILY is a new way; one more sprite is not)
VFX_FAMILY = {"mesh": "mesh", "sprite": "flipbook", "debris": "particles", "swarm": "particles", "trail": "particles",
              "beam": "beam", "screen": "camera", "lens": "camera", "fov": "camera", "shake": "camera",
              "highlight": "camera", "light": "light", "glow": "light", "decal": "ground", "crater": "ground",
              "impact": "ground", "world": "world"}
# anim: the source a clip is built from (kit/cmd/anim.luau compile) - a timing pass (.feel) or an export (.warp) is none
ANIM_SOURCES = (("gait", ".gait.json"), ("move", ".move.json"), ("pose", ".pose.json"), ("import", ".import.json"),
                ("derive", ".derive.json"), ("rearm", ".rearm.json"), ("blend", ".blend"))
SYNTH_SOURCES = {"sine", "square", "saw", "triangle", "noise", "fm", "click", "karplus", "modal"}
# the words a route token adds to the lesson query (the lessons about THAT way of making rank in)
ROUTE_WORDS = {
    "vfx": {"mesh": "mesh shell textured neon plastic", "flipbook": "flipbook sprite sheet frames",
            "particles": "particles debris swarm trail", "beam": "beam", "camera": "camera shake screen",
            "light": "light glow", "ground": "ground decal crater", "world": "world"},
    "anim": {"gait": "gait locomotion walk run", "move": "move keyed poses swing", "pose": "pose key poses rig",
             "import": "import footage library", "blend": "blender keyed", "rearm": "rearm weapon"},
    "sfx": {"recorded": "recording sample real layered", "synth": "synth synthesis oscillator"},
    "world": {"terrain": "terrain heightmap ridges rivers erosion painter", "meshes": "mesh skins props"},
}
SOURCE_EXT = tuple(ext for _t, ext in ANIM_SOURCES) + (".py", ".json")
PATH_TOKEN = re.compile(r"[\w./\\-]+\.(?:json|py|blend|png|jpg|wav|ogg|mp3|glb|fbx|obj|exr|md)\b", re.IGNORECASE)


def _read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return None


def _json(path):
    try:
        return json.loads(_read(path) or "")
    except ValueError:
        return None


def _spec(piece_dir, name):
    """the piece's spec as a dict ({} when missing, unreadable or not an object)"""
    v = _json(os.path.join(piece_dir, f"{name}.json"))
    return v if isinstance(v, dict) else {}


def _is_sets(piece_dir):
    return piece_dir.replace("\\", "/").rstrip("/").endswith("sounds/sets")


def project_root(lane, piece_dir):
    """the project a piece's folder sits in ('' = the kit home, 'games/<G>/' a game), from its lane folder"""
    d = os.path.relpath(os.path.abspath(piece_dir), ROOT).replace("\\", "/").rstrip("/")
    d = "" if d == "." else d
    suffix = LANE_DIR[lane]
    if lane == "sfx" and d.endswith("assets/sounds/sets"):
        suffix = "assets/sounds/sets"
    return d[: -len(suffix)] if d.endswith(suffix) else ""


def _source_files(v):
    """the file paths a build value names (one path, a list, a comma-joined string): tokens with a known extension"""
    out = []
    for x in (v if isinstance(v, list) else [v]):
        if isinstance(x, str):
            out += [t for t in PATH_TOKEN.findall(x) if t.lower().endswith(SOURCE_EXT)]
    return out


def _strings(v):
    if isinstance(v, str):
        yield v
    elif isinstance(v, dict):
        for x in v.values():
            yield from _strings(x)
    elif isinstance(v, list):
        for x in v:
            yield from _strings(x)


# ------------------------------------------------------------------------------------------------------- the route
def _vfx_route(piece_dir, name):
    spec = _spec(piece_dir, name)
    toks = set()
    for layer in spec.get("layers") or []:
        if isinstance(layer, dict):
            fam = VFX_FAMILY.get(str(layer.get("kind", "")).lower())
            if fam:
                toks.add(fam)
    return toks


def _anim_sources(b):
    """the build block's SOURCE values only (source, sources, move_file, any *_file / *_files key) - never its builder,
    its base clip, its key poses or its notes (a note naming a file is no source)"""
    for k, v in b.items():
        if k in ("source", "sources", "move_file") or k.endswith(("_file", "_files")):
            yield v


def _anim_route(piece_dir, name):
    """the dossier's build block: its builder (strike, fp_weapon, ...) and the kinds of source its files are (a .move /
    .pose / .gait / .import / .derive / .rearm file, a .blend, a script) - a dossier with no build block has none"""
    d = _spec(piece_dir, name)
    b = d.get("build") if isinstance(d.get("build"), dict) else {}
    toks = set()
    if isinstance(b.get("builder"), str) and b["builder"].strip():
        toks.add(f"builder {b['builder'].strip()}")
    for v in _anim_sources(b):
        for p in _source_files(v):
            low = p.lower()
            toks |= {tok for tok, ext in ANIM_SOURCES if low.endswith(ext)}
            if low.endswith(".py"):
                toks.add("script")
    return toks


def _ui_route(piece_dir, name):
    spec = _spec(piece_dir, name)
    toks = set()
    if isinstance(spec.get("identity"), str):
        toks.add(f"identity {spec['identity']}")
    try:
        sys.path.insert(0, os.path.join(ROOT, "kit", "ui"))
        import routes as UR  # noqa: PLC0415  (kit/ui/routes.py: every piece's route from its sidecars)
        rows = UR.screen_routes(spec, os.path.join(piece_dir, "art"))
        toks |= {r for _p, _piece, r, _why in rows if r and r != "unknown"}  # (a piece with no art yet is no way)
    except Exception:  # noqa: BLE001  (a spec the routes table cannot read: its identity still counts)
        pass
    return toks


def _sfx_route(piece_dir, name):
    """recorded (a real recording in its layers: the owner's 'pure synth is audio slop', 2026-10-13) and/or synth; a
    set reads its shared DNA and every member's layers"""
    spec = _spec(piece_dir, name)
    layers = list(spec.get("layers") or [])
    dna = spec.get("dna") if isinstance(spec.get("dna"), dict) else {}
    layers += list(dna.get("layers") or [])
    for m in (spec.get("members") or {}).values() if isinstance(spec.get("members"), dict) else []:
        if isinstance(m, dict):
            layers += list(m.get("layers") or [])
    toks = set()
    for layer in layers:
        if isinstance(layer, dict):
            if "sample" in layer or str(layer.get("source", "")).lower() == "sample":
                toks.add("recorded")
            elif str(layer.get("source", "sine")).lower() in SYNTH_SOURCES:
                toks.add("synth")
    return toks


def _world_route(piece_dir, name):
    """terrain (heightmap land: its ridges and rivers) and/or meshes (mesh skins on its generators: the owner's
    SampleIsle 3/10 on castle-mesh skins, 2026-10-28)"""
    spec = _spec(piece_dir, name)
    toks = set()
    if spec.get("terrain"):
        toks.add("terrain")
    blob = json.dumps(spec.get("build") or [])
    if re.search(r'"(?:mesh|meshes|meshId|mesh_id|skin)"\s*:', blob):
        toks.add("meshes")
    return toks


def route(lane, name, piece_dir):
    """the piece's route now: sorted tokens"""
    fn = {"vfx": _vfx_route, "anim": _anim_route, "ui": _ui_route, "sfx": _sfx_route, "world": _world_route}.get(lane)
    return tuple(sorted(fn(piece_dir, name))) if fn else ()


def route_words(lane, toks):
    words = ROUTE_WORDS.get(lane, {})
    return " ".join(words.get(t, re.sub(r"^(identity|builder) ", "", t).replace("_", " ")) for t in toks)


def text_of(toks):
    return ", ".join(toks) if toks else "none"


def anim_piece_of(clip, piece_dir):
    """the dossier whose build block makes this clip: one of its source FILES is named after it, or a gesture pattern
    matches it - never a builder, a base or any other word"""
    if os.path.isfile(os.path.join(piece_dir, f"{clip}.json")):
        return clip
    low = clip.lower()
    for f in sorted(os.listdir(piece_dir)) if os.path.isdir(piece_dir) else []:
        if not f.endswith(".json") or f.startswith("_"):
            continue
        dossier = _json(os.path.join(piece_dir, f))
        b = dossier.get("build") if isinstance(dossier, dict) else None
        if not isinstance(b, dict):
            continue
        g = b.get("gestures")
        if isinstance(g, dict) and any(isinstance(x, str) and fnmatch.fnmatch(low, x.lower()) for x in g):
            return f[:-5]  # (clip patterns: "DTDrillSpin*")
        for v in _anim_sources(b):
            for x in _source_files(v):
                if os.path.basename(x).split(".")[0].lower() == low:
                    return f[:-5]
    return None


OUTPUT_SUFFIXES = (".lessons.md", ".clock.json", ".look.json", ".verdict.json", ".judge.json", ".metrics.json")


def _inside(path, folder):
    a, b = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(folder))
    return a.startswith(b.rstrip("\\/") + os.sep)


def piece_files(lane, name, piece_dir):
    """the files a piece is MADE of (its digest): its spec; every file its spec names that lives in its project's assets
    (never a kit tool, a note, a build output, anything outside); ui: its identity pack and its art pieces' files; anim:
    the sources of the clips its gesture patterns build (in assets/animations). A look's own outputs (<name>.look.json,
    .verdict.json, ...) are never inputs: a look must not read as a change."""
    spec_path = os.path.join(piece_dir, f"{name}.json")
    spec = _spec(piece_dir, name)
    root = os.path.join(ROOT, project_root(lane, piece_dir))
    assets = os.path.join(root, "assets")
    files = []
    for st in _strings(spec):
        for t in PATH_TOKEN.findall(st):
            for base in (root, piece_dir, os.path.dirname(piece_dir.rstrip("/\\"))):
                cand = os.path.normpath(os.path.join(base, t))
                if os.path.isfile(cand):
                    files.append(cand)
                    break
    if lane == "ui":
        if isinstance(spec.get("identity"), str):
            files.append(os.path.join(piece_dir, "identities", f"{spec['identity']}.json"))
        try:
            sys.path.insert(0, os.path.join(ROOT, "kit", "ui"))
            import routes as UR  # noqa: PLC0415
            for _p, idn, piece in UR.pieces_of(spec):
                art = os.path.join(piece_dir, "art", idn or "")
                if piece and os.path.isdir(art):
                    files += [os.path.join(art, f) for f in sorted(os.listdir(art)) if f.split(".")[0] == piece]
        except Exception:  # noqa: BLE001  (a spec the routes table cannot read: its own files still count)
            pass
    if lane == "anim":
        b = spec.get("build") if isinstance(spec.get("build"), dict) else {}
        pats = [x.lower() for x in b.get("gestures") or {} if isinstance(x, str)] if isinstance(b.get("gestures"), dict) else []
        anims = os.path.join(assets, "animations")
        if pats and os.path.isdir(anims):
            files += [os.path.join(anims, f) for f in sorted(os.listdir(anims)) if f.lower().endswith(SOURCE_EXT)
                      and any(fnmatch.fnmatch(f.split(".")[0].lower(), x) for x in pats)]
    seen, out = set(), []
    for f in [spec_path] + files:
        k = os.path.normcase(os.path.abspath(f))
        if k in seen or not os.path.isfile(f) or f.lower().endswith(OUTPUT_SUFFIXES):
            continue
        if f is not spec_path and not _inside(f, assets):
            continue
        seen.add(k)
        out.append(f)
    return out


_HASHED = {}  # (path, mtime, size) -> its sha1: a texture many presets name is read once per run


def _file_hash(path):
    st = os.stat(path)
    k = (os.path.normcase(os.path.abspath(path)), st.st_mtime_ns, st.st_size)
    if k not in _HASHED:
        with open(path, "rb") as fh:
            _HASHED[k] = hashlib.sha1(fh.read()).hexdigest()
    return _HASHED[k]


def digest(lane, name, piece_dir):
    h = hashlib.sha1()
    for f in piece_files(lane, name, piece_dir):
        h.update(os.path.basename(f).encode() + b"\0" + _file_hash(f).encode())
    return h.hexdigest()[:16]


# ------------------------------------------------------------------------------------------------------- the clock
def spec_tier(lane, name, piece_dir, hero_ok=False):
    """the piece's tier: its spec's "tier" (a screen's "quality"), else the lane's default (a sound set: complex);
    hero / aaa only with the owner's approval of the piece (kit approve), else complex"""
    spec = _json(os.path.join(piece_dir, f"{name}.json"))
    tier = DEFAULT_TIER[lane]
    if lane == "sfx" and _is_sets(piece_dir):
        tier = "complex"
    said = (spec.get("quality") if lane == "ui" else spec.get("tier")) if isinstance(spec, dict) else None
    if isinstance(said, str) and said.lower() in TIERS:
        tier = "simple" if said.lower() == "prop" else said.lower()
    if tier in ("hero", "aaa") and not hero_ok:
        tier = "complex"  # (a hero's hour is the owner's to give: kit approve <lane> <name> "<his words>" --by owner)
    return tier


def clock_path(lane, name, piece_dir):
    """<project>/assets/clocks/<lane>/<name>.clock.json (a sound set's under sfx-sets: a sound and a set may share a
    name)"""
    sub = "sfx-sets" if lane == "sfx" and _is_sets(piece_dir) else lane
    return os.path.join(ROOT, project_root(lane, piece_dir), "assets", "clocks", sub, f"{name}.clock.json")


def _baseline(lane, piece_dir):
    """the lane's record of every piece's digest as last seen (the rebuild of every piece, a look): -> (path, dict)"""
    path = os.path.join(ROOT, project_root(lane, piece_dir), "assets", "clocks", lane, "_built.json")
    b = _json(path)
    return path, (b if isinstance(b, dict) else {})


def _base_key(lane, name, piece_dir):
    root = os.path.join(ROOT, project_root(lane, piece_dir))
    return os.path.relpath(os.path.abspath(piece_dir), root).replace("\\", "/") + "/" + name


def read_clock(lane, name, piece_dir, now=None):
    """-> {started, tier, budget_min, extended_min, elapsed_min, left_min, over, attempt} or None (never started)"""
    c = _json(clock_path(lane, name, piece_dir))
    if not isinstance(c, dict) or not isinstance(c.get("started"), (int, float)):
        return None
    tier = c.get("tier") if c.get("tier") in TIERS else "simple"
    ext = [e for e in c.get("extensions") or [] if isinstance(e, dict)]
    extra = sum(PL._minutes(e.get("minutes")) for e in ext)
    budget = TIERS[tier]
    t = now or time.time()
    start = float(c["started"])
    deadline = PL.clock_deadline(start, budget, ext)  # (an extension given after the run-out counts from then)
    return {"started": start, "tier": tier, "budget_min": budget, "extended_min": extra,
            "elapsed_min": round(max(0.0, (t - start) / 60.0), 1), "left_min": round((deadline - t) / 60.0, 1),
            "over": t > deadline, "attempt": int(c.get("attempt") or 1)}


def write_clock(lane, name, piece_dir, tier="simple", extend=None, words=None, restart=False, now=None):
    """start (the first build), extend (the owner's minutes + words) or restart (a new attempt, his words) -> the clock"""
    path = clock_path(lane, name, piece_dir)
    now = now or time.time()
    c = _json(path)
    if not isinstance(c, dict) or not isinstance(c.get("started"), (int, float)):
        c = {"started": now, "attempt": 1, "extensions": []}
    if restart:
        c = {"started": now, "attempt": int(c.get("attempt") or 1) + 1, "extensions": [],
             "restarted": {"words": words, "at": now}}
    if extend:
        c.setdefault("extensions", []).append({"minutes": float(extend), "words": words, "at": now})
    if restart or c.get("tier") not in TIERS:  # (frozen for the attempt: set when it starts, kept by an extension)
        c["tier"] = tier if tier in TIERS else "simple"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(c, fh, indent=1)
        fh.write("\n")
    return read_clock(lane, name, piece_dir, now)


# --------------------------------------------------------------------------------------------- the answers record
def sheet_key(piece_dir, name):
    d = os.path.relpath(os.path.abspath(piece_dir), ROOT).replace("\\", "/").rstrip("/")
    return f"{name}.lessons.md" if d == "." else f"{d}/{name}.lessons.md"


def _answers_path():
    return os.path.join(ROOT, "board", "answers.json")


def _entry_key(rec, piece_dir, name):
    """the record's key for this sheet, in any letter case (pieceDir matches names so)"""
    want = sheet_key(piece_dir, name)
    if want in rec:
        return want
    low = want.lower()
    return next((k for k in rec if isinstance(k, str) and k.lower() == low), None)


def answered_route(piece_dir, name):
    """the route its lessons sheet was answered for (board/answers.json), None when it has none recorded, or False when
    the piece has no sheet record at all (an empty route - written {} by the Luau side - is the empty route)"""
    rec = _json(_answers_path())
    key = _entry_key(rec, piece_dir, name) if isinstance(rec, dict) else None
    e = rec.get(key) if key else None
    if not isinstance(e, dict):
        return False
    if "route" not in e:
        return None
    r = e.get("route")
    return tuple(sorted(x for x in r if isinstance(x, str))) if isinstance(r, list) else ()


def _write_text(path, text):
    """write via a temp file + replace: a reader never sees half a file"""
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)


def stamp_route(piece_dir, name, toks, more=()):
    """a sheet recorded before routes were kept takes the route it first builds on -> True when written. more: further
    (piece_dir, name, toks) to stamp in the same write (a rebuild of every piece)"""
    path = _answers_path()
    rec = _json(path)
    if not isinstance(rec, dict):
        return False
    wrote = False
    for d, n, t in [(piece_dir, name, toks)] + list(more):
        key = _entry_key(rec, d, n)
        if key and isinstance(rec.get(key), dict) and "route" not in rec[key]:
            rec[key]["route"] = list(t)
            wrote = True
    if wrote:
        _write_text(path, json.dumps(rec, indent=2, ensure_ascii=False) + "\n")
    return wrote


# ------------------------------------------------------------------------------------------------ the check itself
def what_there_is(lane, name, piece_dir):
    root = os.path.join(ROOT, project_root(lane, piece_dir))
    cands = {"vfx": [os.path.join(piece_dir, f"{name}.json")],
             "ui": [os.path.join(piece_dir, f"{name}.json"), os.path.join(root, "src", "ui", f"{name}.model.json")],
             "anim": [os.path.join(piece_dir, f"{name}.json"),
                      os.path.join(os.path.dirname(piece_dir.rstrip("/\\")), f"{name}.clip.json")],
             "sfx": [os.path.join(piece_dir, f"{name}.json")], "world": [os.path.join(piece_dir, f"{name}.json")]}
    show = {"vfx": f"play it for him: lune run kit vfx play {name}", "ui": f"his view: lune run kit ui look {name}",
            "anim": f"its sheet for him: lune run kit anim look {name}", "sfx": f"for his ears: lune run kit sfx booth {name}",
            "world": f"walk it for him: lune run kit world look {name}"}
    have = [os.path.relpath(p, ROOT).replace(os.sep, "/") for p in cands.get(lane, []) if os.path.isfile(p)]
    return [f"  - {p}" for p in have] + [f"  - {show[lane]}"]


def prebuild(lane, name, piece_dir, tier=None, use_clock=True, now=None, hero_ok=False, look=False):
    """-> (stop, summary, next_action, lines): the clock, then the route its lessons were answered for. tier: None = the
    spec's (spec_tier). look: playing / capturing the piece as it is - its clock starts only when the piece CHANGED since
    it was last seen (a look at an untouched piece starts nothing); a clock it has is held as a build's.
    use_clock=False: no clock at all"""
    now = now or time.time()
    note = []
    clock = read_clock(lane, name, piece_dir, now) if use_clock else None
    start = use_clock and clock is None
    if start and look:
        try:
            bpath, base = _baseline(lane, piece_dir)
            key, dig0 = _base_key(lane, name, piece_dir), digest(lane, name, piece_dir)
            was_seen = base.get(key)
            if was_seen != dig0:
                base[key] = dig0
                os.makedirs(os.path.dirname(bpath), exist_ok=True)
                _write_text(bpath, json.dumps(base, indent=1, ensure_ascii=False) + "\n")
            start = was_seen is not None and was_seen != dig0  # (changed since it was last seen: being worked on)
        except OSError as e:
            note.append(f"its last-seen record could not be written ({type(e).__name__})")
            start = False
    if start:
        try:
            clock = write_clock(lane, name, piece_dir, tier=tier or spec_tier(lane, name, piece_dir, hero_ok), now=now)
            note.append(f"clock started: {clock['budget_min']:g} min ({clock['tier']})")
        except OSError as e:  # (a clock that cannot be written refuses nothing: the next build tries again)
            note.append(f"its clock could not be written ({type(e).__name__}): the next build tries again")
    dig = digest(lane, name, piece_dir)
    raw = _json(clock_path(lane, name, piece_dir)) if use_clock else None
    if clock and clock["over"] and isinstance(raw, dict) and raw.get("built") == dig:
        note.append(f"past its budget ({clock['elapsed_min']:g} of {clock['budget_min']:g} min) but unchanged since its "
                    "last build: what there is, as it was (any change needs the owner's words)")
        return False, f"{lane} {name}: unchanged since its last build - looked at / rebuilt as it was", "show the owner", note
    if clock and clock["over"]:
        spent = (f"{clock['elapsed_min']:g} of {clock['budget_min']:g}"
                 + (f"+{clock['extended_min']:g}" if clock["extended_min"] else "")
                 + f" min ({clock['tier']}, attempt {clock['attempt']})")
        lines = [f"STOP — BUDGET: {spent}: no change to {lane} {name} builds past its budget",
                 "what there is (show the owner):"]
        lines += what_there_is(lane, name, piece_dir)
        lines.append("still open about it:")
        lines += [f"  - {i} ({s}): {t[:100]}" for i, s, t in PL.open_cards(name, ROOT)] or ["  - no open card names it"]
        lines += ["only his words reopen it:",
                  f'  - more time on this attempt: lune run kit clock {lane} {name} --extend <minutes> "<his words>"',
                  f'  - a new attempt: lune run kit clock {lane} {name} --restart "<his words>"']
        return (True, f"{lane} {name}: STOP — BUDGET: {spent}: no change builds past the budget",
                "show the owner what there is and what is still open (listed above); only his words reopen it: "
                f'lune run kit clock {lane} {name} --extend <minutes> "<his words>" (or --restart "<his words>")', lines)
    now_route = route(lane, name, piece_dir)
    was = answered_route(piece_dir, name)
    gained = tuple(sorted(set(now_route) - set(was))) if was not in (None, False) else ()
    if gained:
        lines = [f"STOP — ROUTE: {lane} {name} is made a new way (+ {text_of(gained)}: {text_of(was)} -> "
                 f"{text_of(now_route)}) since its lessons were answered",
                 "  its answers were written for the old route: each matched lesson is asked again, for the new one",
                 f"  lune run kit answer {lane} {name} --reroute   (the old answers kept to read; copying one does not count)"]
        return (True, f"{lane} {name}: STOP — ROUTE changed ({text_of(was)} -> {text_of(now_route)}) since its lessons "
                f"were answered (new: {text_of(gained)})",
                f"lune run kit answer {lane} {name} --reroute, answer each lesson for the new route, then build", lines)
    if was is None:
        try:
            if stamp_route(piece_dir, name, now_route):
                note.append(f"its lessons sheet takes its route: {text_of(now_route)}")
        except OSError as e:
            note.append(f"its route could not be recorded ({type(e).__name__}): the next build tries again")
    if use_clock and isinstance(raw, dict):
        try:  # (the piece as this build makes it: past the budget only this, unchanged, builds again)
            c = _json(clock_path(lane, name, piece_dir))
            if isinstance(c, dict) and c.get("built") != dig:
                c["built"] = dig
                with open(clock_path(lane, name, piece_dir), "w", encoding="utf-8") as fh:
                    json.dump(c, fh, indent=1)
                    fh.write("\n")
        except OSError as e:
            note.append(f"its clock could not record this build ({type(e).__name__})")
    left = (f"{clock['left_min']:g} min left of its budget" if clock else
            "no clock (a look at it unchanged)" if look else "no clock read" if not use_clock else "its clock unread")
    return False, f"{lane} {name}: {left}, its lessons answered for its route", "build", note


def _piece_specs(d):
    """a lane folder's piece specs: <name>.json (never a _registry, never a <name>.<kind>.json beside a piece)"""
    if not os.path.isdir(d):
        return []
    return [f[:-5] for f in sorted(os.listdir(d)) if f.endswith(".json") and not f.startswith("_") and f.count(".") == 1]


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
        fh.write("\n")


def prebuild_all(lane, project, approved=(), now=None, dirs=None):
    """a rebuild of every piece of the lane in one project (kit ui / kit sfx all / kit vfx / kit anim with no name,
    kit world) -> (stop, summary, next_action, lines). Every piece is read: one past its budget and changed since its
    last build is held back, and so is one whose route gained a way since its lessons were answered. A piece new or
    CHANGED since the last rebuild of every piece (the digests kept in <project>/assets/clocks/<lane>/_built.json) is
    being worked on: its clock starts here (the first rebuild only records the digests, so no old piece is clocked).
    Nothing is written when a piece is held back. dirs: the folders the rebuild builds (default: the lane's, + a sound
    lane's sets)."""
    now = now or time.time()
    base = os.path.join(ROOT, project)
    dirs = dirs or ([os.path.join(base, LANE_DIR[lane])]
                    + ([os.path.join(base, "assets", "sounds", "sets")] if lane == "sfx" else []))
    bpath = os.path.join(base, "assets", "clocks", lane, "_built.json")
    seen = _json(bpath)
    seen = seen if isinstance(seen, dict) else {}
    ok_hero = {a.lower() for a in approved}
    held, note, starts, builds, digests = [], [], [], [], {}
    for d in dirs:
        rel = os.path.relpath(d, base).replace("\\", "/")
        first = not any(k.rsplit("/", 1)[0] == rel for k in seen)  # (this folder's first rebuild: record only)
        for name in _piece_specs(d):
            dig = digest(lane, name, d)
            digests[f"{rel}/{name}"] = dig
            clock = read_clock(lane, name, d, now)
            raw = _json(clock_path(lane, name, d))
            if clock and clock["over"] and isinstance(raw, dict) and raw.get("built") != dig:
                held.append(f"{name}: past its budget ({clock['elapsed_min']:g} of {clock['budget_min']:g} min) and "
                            f"changed since its last build - only his words: lune run kit clock {lane} {name} --extend "
                            '<minutes> "<his words>"')
            elif clock:
                if isinstance(raw, dict) and raw.get("built") != dig:
                    builds.append((name, d, dig))
            elif not first and seen.get(f"{rel}/{name}") != dig:
                starts.append((name, d, dig))
    rec = _json(_answers_path())
    keep = {os.path.normcase(os.path.abspath(d)) for d in dirs}
    stamps = []
    for key, e in (rec.items() if isinstance(rec, dict) else []):
        if not (isinstance(e, dict) and e.get("dept") == lane):
            continue
        pdir = os.path.join(ROOT, os.path.dirname(key))
        if os.path.normcase(os.path.abspath(pdir)) not in keep:
            continue
        name = os.path.basename(key)[: -len(".lessons.md")]
        if not os.path.isfile(os.path.join(pdir, f"{name}.json")):
            continue
        now_route = route(lane, name, pdir)
        if "route" not in e:  # (recorded before routes were kept: it takes the route this rebuild builds it on)
            stamps.append((pdir, name, now_route))
            continue
        was = e["route"] if isinstance(e["route"], list) else []  # (Lune writes the empty route as {})
        gained = sorted(set(now_route) - set(x for x in was if isinstance(x, str)))
        if gained:
            held.append(f"{name}: made a new way (+ {', '.join(gained)}) since its lessons were answered - "
                        f"lune run kit answer {lane} {name} --reroute")
    if held:
        return (True, f"{lane} (every piece): STOP — {len(held)} piece(s) held back: {held[0]}",
                "deal with each held piece (listed above), then build again", [f"STOP — {h}" for h in held])
    try:
        for name, d, dig in starts:
            c = write_clock(lane, name, d, tier=spec_tier(lane, name, d, name.lower() in ok_hero), now=now)
            builds.append((name, d, dig))
            note.append(f"{lane} {name}: new or changed since the last rebuild - its clock started: "
                        f"{c['budget_min']:g} min ({c['tier']})")
        for name, d, dig in builds:
            c = _json(clock_path(lane, name, d))
            if isinstance(c, dict):
                c["built"] = dig
                _write_json(clock_path(lane, name, d), c)
        seen.update(digests)
        _write_json(bpath, seen)
        if stamps and stamp_route(*stamps[0], more=stamps[1:]):
            note.append(f"{len(stamps)} lessons sheet(s) took the route they were built on")
    except OSError as e:  # (a record that cannot be written refuses nothing: the next rebuild tries again)
        note.append(f"the lane's build record could not be written ({type(e).__name__}): the next rebuild tries again")
    said = f", {len(starts)} clock(s) started" if starts else ""
    return False, f"{lane} (every piece): nothing held back{said}", "build", note


# ---------------------------------------------------------------------------------------------------------- cli
def main(argv):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    def emit(status, summary, action, code=None, **extra):
        print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": action, **extra}))
        return code if code is not None else (0 if status == "pass" else 1)

    def opt(flag, default=None):
        if flag in argv:
            k = argv.index(flag)
            if k + 1 < len(argv) and not argv[k + 1].startswith("--"):
                return argv[k + 1]
        return default

    if len(argv) >= 2 and argv[0] == "prebuild-all" and argv[1] in LANES:
        root, dirs = opt("--root"), None
        if opt("--dir"):  # (the folder the rebuild builds: its project is what is left of the path)
            dirs = [os.path.join(ROOT, opt("--dir"))]
            root = project_root(argv[1], dirs[0]) if root is None else root
        approved = [a for a in (opt("--approved") or "").split(",") if a]
        stop, summary, action, lines = prebuild_all(argv[1], root or "", approved=approved, dirs=dirs)
        for ln in lines:
            print(ln)
        return emit("fail" if stop else "pass", summary, action)
    if len(argv) >= 3 and argv[0] == "piece" and argv[1] == "anim":  # (a clip -> the dossier that builds it)
        piece = anim_piece_of(argv[2], opt("--dir") or os.path.join(ROOT, LANE_DIR["anim"]))
        return emit("pass", f"anim {argv[2]}: built by the dossier {piece}" if piece else
                    f"anim {argv[2]}: no dossier builds it", "none", piece=piece)
    if len(argv) < 3 or argv[0] not in ("prebuild", "route", "extend", "restart") or argv[1] not in LANES:
        return emit("fail", "lanecheck: prebuild|prebuild-all|route|piece|extend|restart <lane> <name> --dir <folder>",
                    "python kit/tools/lanecheck.py prebuild vfx <name> --dir assets/effects", 2)
    cmd, lane, name = argv[0], argv[1], argv[2]
    piece_dir = opt("--dir") or os.path.join(ROOT, LANE_DIR[lane])
    if lane == "anim" and not os.path.isfile(os.path.join(piece_dir, f"{name}.json")):
        piece = anim_piece_of(name, piece_dir)
        if piece is None:
            return emit("pass", f"anim {name}: no dossier builds this clip - nothing to clock or route", "build")
        name = piece
    tier = opt("--tier")  # (None: the spec's own - spec_tier; --hero-ok: the owner approved the piece's hero hour)
    if cmd == "route":
        toks = route(lane, name, piece_dir)
        return emit("pass", f"{lane} {name}: route {text_of(toks)}", "none", route=list(toks),
                    words=route_words(lane, toks))
    if cmd == "extend":
        mins, words = (argv[3] if len(argv) > 3 else ""), (argv[4] if len(argv) > 4 else "")
        try:
            m = float(mins)
        except ValueError:
            m = 0.0
        if not (math.isfinite(m) and 0 < m <= PL.MAX_EXTEND_MIN) or not words or words.startswith("--"):
            return emit("fail", f"clock --extend: needs the minutes (over 0, at most {PL.MAX_EXTEND_MIN}) and the "
                        "owner's words", f'lune run kit clock {lane} {name} --extend 10 "<the owner words>"', 2)
        c = write_clock(lane, name, piece_dir, tier=spec_tier(lane, name, piece_dir, "--hero-ok" in argv), extend=m,
                        words=words)
        return emit("pass", f"clock {lane} {name}: +{m:g} min on the owner's words - {c['left_min']:g} min left",
                    "build, then show him")
    if cmd == "restart":
        words = argv[3] if len(argv) > 3 and not argv[3].startswith("--") else ""
        if not words:
            return emit("fail", "clock --restart: needs the owner's words (a new attempt)",
                        f'lune run kit clock {lane} {name} --restart "<the owner words>"', 2)
        c = write_clock(lane, name, piece_dir, tier=tier or spec_tier(lane, name, piece_dir, "--hero-ok" in argv),
                        restart=True, words=words)
        return emit("pass", f"clock {lane} {name}: attempt {c['attempt']} on the owner's words - {c['budget_min']:g} "
                    f"min ({c['tier']})", "build, then show him")
    stop, summary, action, lines = prebuild(lane, name, piece_dir, tier=tier, use_clock="--no-clock" not in argv,
                                            hero_ok="--hero-ok" in argv, look="--look" in argv)
    for ln in lines:
        print(ln)
    return emit("fail" if stop else "pass", summary, action)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
