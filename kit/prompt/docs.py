"""docs.py - PROMPT-X's Roblox Engine API grounding (LIMITATIONS_FIXES_V4 9.2 row 1: "docs.py API signatures scoped to
(lane, family, game)"; 9.1 point 1: models forget the engine, so the prompt carries it).

The reference is the one kit/tools/docs.py reads: the Roblox Studio on this machine ships every class member, global and
enum item with its description (<Studio>/content/api_docs/en-us.json), and the kit's own type file
(kit/types/globalTypes.d.luau) holds each member's declared Luau signature. Nothing is downloaded; nothing of Roblox's
text is copied into the repo (a compiled prompt quotes one line per API it names).

    template   each routed lane's template `api` names: checked to exist and not to be deprecated, with the signature
    prompt     the owner's own words looked up INSIDE the lane's scope (LANE_SCOPE: the classes that lane builds with,
               their engine parents too) - "particles emit faster with light emission" in vfx finds
               ParticleEmitter.LightEmission, never a Players event; a member counts only when a word names it
    family     the asset families the prompt matched (kit/knowledge/families.json) add their names' words
    game       the services the active game's code already calls (game:GetService("X")) lift those classes; with no game
               the kit's own runtime (src/kit) is the code, and Sample Game's folder is never read

scoped(...) -> {"api": [{name, kind, doc, signature, scope, lane, verified}], "problems": [...], "scope": {...}}.
With no Studio on the machine every template name is kept, marked unverified, and nothing is looked up by words."""

import os
import re

try:
    from . import models
except ImportError:
    import models

# the classes each lane builds with (a curated scope, checked against the reference by the tests: every class exists)
LANE_SCOPE = {
    "3d": ("MeshPart", "SurfaceAppearance", "BasePart", "Model", "WrapLayer", "EditableMesh", "AssetService", "MaterialVariant"),
    "vfx": ("ParticleEmitter", "Beam", "Trail", "Attachment", "Highlight", "PointLight", "SpotLight", "TweenService", "Camera"),
    "anim": ("Animator", "AnimationTrack", "Animation", "KeyframeSequence", "Keyframe", "Pose", "Motor6D", "Humanoid", "AnimationController"),
    "world": ("Terrain", "Lighting", "Atmosphere", "Sky", "Clouds", "Workspace", "BasePart", "PathfindingService"),
    "ui": (
        "GuiObject", "Frame", "TextLabel", "TextButton", "ImageLabel", "ImageButton", "ScreenGui", "UIListLayout", "UIFlexItem",
        "UIStroke", "UIGradient", "UICorner", "UIScale", "TweenService", "GuiService", "UserInputService",
    ),
    "sfx": ("Sound", "SoundService", "SoundGroup", "AudioPlayer", "AudioEmitter", "AudioListener", "AudioReverb", "AudioCompressor", "AudioFader", "Wire"),
    "systems": (
        "RemoteEvent", "RemoteFunction", "UnreliableRemoteEvent", "Players", "Player", "DataStoreService", "GlobalDataStore",
        "RunService", "Workspace", "CollectionService", "MemoryStoreService", "task",
    ),
}
GENERIC_BASES = {"Instance", "PVInstance", "Object"}  # a parent every class has adds noise, not scope
WORD_STOP = set(
    "make made with like feel that this have from into more very sure look good make want need some thing stuff "
    "really just also then than when what which where while does done will would should could ultimate".split()
)
# plain-English words that are also API verbs or nouns: alone they name nothing ("a fire katana" is no
# RemoteEvent:FireClient); beside another word of the same name they count
AMBIGUOUS = {"fire", "play", "player", "stop", "light", "clean", "part", "fill", "size", "color", "time", "text", "image",
             "move", "touch", "change", "value", "name", "parent", "enabled", "visible", "position", "speed"}
K_LEAD, K_OTHER, K_TOTAL = 2, 1, 4  # the prompt-scoped names added: the lead lane's two, one per other lane, four in all


def _excluded_games():
    """the project's private games (profiles.core.exclude_games, lower case): their scripts are never read for names"""
    return [g.lower() for g in models.core_profile().get("exclude_games") or [] if isinstance(g, str) and g.strip()]
_REF = {"engine": None, "index": None, "types": None, "tried": False, "scoped": {}, "game": {}}


# ---------------------------------------------------------------------------------------------- the reference
def engine():
    """kit/tools/docs.py, loaded by path (its own module name: never the kit/prompt one)"""
    if _REF["engine"] is None:
        import importlib.util

        spec = importlib.util.spec_from_file_location("kit_prompt_docs_engine", os.path.join(models.root(), "kit", "tools", "docs.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _REF["engine"] = mod
    return _REF["engine"]


def index():
    """{name: (kind, doc)} from Studio's reference, or None (KIT_PROMPT_DOCS=0, or no Studio on this machine)"""
    if not _REF["tried"]:
        _REF["tried"] = True
        if os.environ.get("KIT_PROMPT_DOCS") == "0":
            return None
        try:
            eng = engine()
            src = eng.find_source()
            if src:
                # (type_lines also fills the engine's PARENTS: an inherited member is documented on its parent)
                _REF["types"] = eng.type_lines(os.path.join(models.root(), "kit", "types", "globalTypes.d.luau"))
                _REF["index"] = eng.entries(src)
        except Exception:  # (no Studio, or an unreadable reference: the names go unverified, said so)
            _REF["index"] = _REF["types"] = None
    return _REF["index"]


def reset():
    """forget the loaded reference (tests switch KIT_PROMPT_DOCS / KIT_API_DOCS)"""
    _REF.update({"index": None, "types": None, "tried": False, "scoped": {}, "game": {}})


def _parents(cls):
    out, seen = [], set()
    parents = engine().PARENTS
    while cls and cls not in seen:
        seen.add(cls)
        out.append(cls)
        cls = parents.get(cls)
    return out


def signature(name):
    """the member's declared Luau signature in call form ('Workspace:GetServerTimeNow(): number',
    'ParticleEmitter.Rate: number'), from the type file - its own class first, then the class it inherits from"""
    types = _REF.get("types") or {}
    m = re.match(r"^(\w+)\.(\w+)$", name or "")
    if not m:
        return None
    cls, member = m.groups()
    line = None
    for c in _parents(cls):
        line = types.get(f"{c}.{member}")
        if line:
            break
    if not line:
        return None
    fm = re.match(r"^function\s+(\w+)\(self(?:,\s*)?(.*)$", line)
    if fm:
        return f"{cls}:{fm.group(1)}({fm.group(2)}"
    fm = re.match(r"^function\s+(\w+)\((.*)$", line)
    if fm:
        return f"{cls}.{fm.group(1)}({fm.group(2)}"
    return f"{cls}.{line}"


def _first_sentence(doc, n=110):
    first = re.split(r"(?<=\.)\s", doc or "", maxsplit=1)[0]
    return first if len(first) <= n else first[: n - 1].rstrip() + "…"


def verify(names, lane=None, scope="template"):
    """-> (rows [{name, kind, doc, signature, scope, lane, verified}], problems [str]); with no local reference every
    name is kept, marked unverified (nothing is invented for it)"""
    idx = index()
    rows, problems = [], []
    for name in names:
        if idx is None:
            rows.append({"name": name, "kind": None, "doc": "", "signature": None, "scope": scope, "lane": lane, "verified": False})
            continue
        hit, _via = engine().exact_name(idx, name)
        if not hit:
            problems.append(f"{name}: not in the Roblox API reference")
            continue
        kind, doc = idx[hit]
        if doc.lower().startswith("deprecated"):
            problems.append(f"{name}: deprecated ({_first_sentence(doc, 120)})")
            continue
        rows.append({"name": name, "kind": kind, "doc": _first_sentence(doc), "signature": signature(name), "scope": scope, "lane": lane, "verified": True})
    return rows, problems


# ---------------------------------------------------------------------------------------------- the scope
def _stem(w):
    return w[:-1] if len(w) > 4 and w.endswith("s") and not w.endswith("ss") else w


def query_words(text):
    """the prompt's words a member name can carry (camelCase split, plurals folded, filler dropped)"""
    return {_stem(w) for w in engine().words(text or "") if len(w) >= 4 and w not in WORD_STOP}


def scope_classes(lane):
    """the lane's classes and the engine classes they inherit from (Workspace -> WorldRoot), generic bases aside"""
    out = []
    for cls in LANE_SCOPE.get(lane, ()):
        for c in _parents(cls) if index() is not None else [cls]:
            if c not in GENERIC_BASES and c not in out:
                out.append(c)
    return out


def _scoped_index(lane):
    """the slice of the reference the lane builds with: its classes, their members, never an enum item or a deprecated
    member (a scoped search reads a few hundred names, not ten thousand)"""
    if lane not in _REF["scoped"]:
        idx = index() or {}
        classes = set(scope_classes(lane))
        sub = {}
        for name, (kind, doc) in idx.items():
            if kind == "enum" or doc.lower().startswith("deprecated"):
                continue
            head = name.split(".")[0]
            if head in classes:
                sub[name] = (kind, doc)
        _REF["scoped"][lane] = sub
    return _REF["scoped"][lane]


def game_services(game):
    """the services the game's code already calls (game:GetService("X")): the active game's src, or the kit's own
    runtime with no game; Sample Game's folder is never read"""
    key = game or ""
    if key in _REF["game"]:
        return _REF["game"][key]
    excluded = _excluded_games()
    if game and game.lower() in excluded:
        _REF["game"][key] = set()
        return set()
    base = os.path.join(models.root(), "games", game, "src") if game else os.path.join(models.root(), "src", "kit")
    found = set()
    for d, _dirs, files in os.walk(base):
        if any(f"/{g}/" in d.replace("\\", "/").lower() + "/" for g in excluded):
            continue
        for f in files:
            if not f.endswith((".luau", ".lua")):
                continue
            try:
                with open(os.path.join(d, f), encoding="utf-8", errors="replace") as fh:
                    found.update(re.findall(r"GetService\(\s*[\"'](\w+)[\"']\s*\)", fh.read()))
            except OSError:
                continue
    _REF["game"][key] = found
    return found


def prompt_names(lane, words, used=(), k=2, services=()):
    """the lane-scoped names the prompt's words name: a word must be a word of the member's (or class's) own name -
    a description alone never pulls an API in; rarer words count more; the game's own services rank first on a tie"""
    import math

    sub = _scoped_index(lane)
    if not sub or not words:
        return []
    eng = engine()
    name_words = {n: {_stem(w) for w in eng.words(n.split(".")[-1])} for n in sub}
    df = {}
    for ws in name_words.values():
        for w in ws:
            df[w] = df.get(w, 0) + 1
    n_all = len(sub)
    rows = []
    for name, ws in name_words.items():
        if name in used:
            continue
        hit = words & ws
        # the words must name the member: half its name's words, or two of them ("player" alone is no reason for
        # GuiService:InspectPlayerFromUserId; "light emission" is ParticleEmitter.LightEmission)
        if not hit or (len(hit) < 2 and (len(hit) / max(1, len(ws)) < 0.5 or hit <= AMBIGUOUS)):
            continue
        s = sum(math.log(1 + n_all / (1 + df.get(w, 0))) for w in hit) * (len(hit) / len(ws)) ** 0.5
        doc_hits = words & {_stem(w) for w in eng.words(sub[name][1][:300])}
        s += 0.25 * len(doc_hits - hit)
        if name.split(".")[0] in services:
            s *= 1.25
        rows.append((s, name))
    rows.sort(key=lambda r: (-r[0], len(r[1]), r[1]))
    return [name for _s, name in rows[:k]]


def scoped(lanes, raw, families=(), game=None):
    """the API names a prompt needs, scoped to (lane, family, game): every lane's template names first, then the names
    the owner's words (and the matched families) name inside each lane's scope -> {api, problems, scope}"""
    names, rows, problems = [], [], []
    for lane in lanes:
        t_names = [a for a in models.template(lane).get("api", []) if a not in names]
        got, bad = verify(t_names, lane, "template")
        names += t_names
        rows += got
        problems += bad
    services = game_services(game) if index() is not None else set()
    fam_words = " ".join(f.split(":", 1)[-1].replace("_", " ") for f in families)
    extra = []
    if index() is not None:
        words = query_words(raw)
        fwords = query_words(fam_words)
        for rank, lane in enumerate(lanes):
            k = K_LEAD if rank == 0 else K_OTHER
            for name in prompt_names(lane, words, names + [r["name"] for r in extra], k, services):
                extra.append({"lane": lane, "name": name, "scope": "prompt"})
            for name in prompt_names(lane, fwords - words, names + [r["name"] for r in extra], 1, services):
                extra.append({"lane": lane, "name": name, "scope": "family"})
        for e in extra[:K_TOTAL]:
            got, _bad = verify([e["name"]], e["lane"], e["scope"])
            for r in got:
                if r["name"].split(".")[0] in services:
                    r["scope"] += "+game"
            rows += got
    return {
        "api": rows,
        "problems": problems,
        "scope": {
            "lanes": {lane: scope_classes(lane) for lane in lanes},
            "families": list(families),
            "game": game or "none (the kit's own runtime, src/kit)",
            "game_services": sorted(services),
            "reference": "local" if index() is not None else "none on this machine (names unverified)",
        },
    }


def line(row):
    """one API row as a prompt line: the exact signature when the type file has it, then the reference's first sentence"""
    head = row.get("signature") or row["name"]
    doc = row.get("doc") or ""
    return f"{head} - {doc}" if doc else head
