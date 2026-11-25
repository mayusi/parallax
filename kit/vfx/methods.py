"""methods.py - the owner's VFX methods, and the METHOD PLAN that makes an effect use them.

    lune run kit vfx methods                       the 104 methods of his list: which the kit has, how, and the tool
    lune run kit vfx methods <words>               find a method by its name, what it does or what it is for
    lune run kit vfx methods --set <set>           a scene's method plan, beat by beat: what is planned, what the
                                                   beat sheet's words call for, what is still open
    lune run kit vfx methods --set <set> --beat N --use id,id [--not id="why not"] [--drop id]
                                                   write one beat's plan into the chart (refs_measured/<set>.chart.json)
    python kit/vfx/methods.py --gate --effects <dir> --name <preset> [--textures <dir>] [--expanded <file>]
                                                   the gate `kit vfx` runs on a preset built from a scene

Why (the owner, 2026-11-13): "every method i mentioned for each pipeline keep going up until they are all mastered and
implmented into each pipeline and enforced in the terms of being used". The register (kit/vfx/methods.json) holds his
104 methods in his words and order, and for each: whether the kit has it, how, and what in a preset PROVES it is used.

The plan lives in the beat chart the owner approves: every beat row of refs_measured/<set>.chart.json carries
    "methods": ["hand_drawn", "mesh", ...]      the methods of his list this beat is made with
    "not": {"hand_drawn": "<why not>"}          a method the beat's own words call for and the plan leaves out
`kit vfx chart` draws both under the beat, in his words, and its approval records the plan he saw.

The gate, for a preset built from that scene (and for each of its variants):
  * every layer's beat is a beat of the chart, and the preset builds at least one of them;
  * every beat the preset builds has a plan, of methods the kit has;
  * every planned method is USED: a layer of that beat that PLAYS proves it (the register's proof) - read from the
    preset as it plays (expanded: a muted layer is gone, a part's layers are in), a layer that draws nothing
    (fully transparent, no size, no life) proving nothing;
  * a beat whose words call for an ASK method (the register's "ask": the kit's way is the scene's way) uses it, or
    says why not - and that reason counts only once the OWNER has seen it, word for word, on the chart he approved
    (an approval recorded by anyone else holds no plan);
  * nothing he saw on the chart he approved has been dropped since.
More methods than the plan are always free. Pieces that existed before the gate are exempt (kit/vfx/scene_gate.json
"methods", frozen). Prints one JSON line {schema, status, summary, next_action, ...}; the gate prints {problems, ...}.
"""

import glob
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REGISTER = os.path.join(HERE, "methods.json")
EFFECTS = os.path.join("assets", "effects")
TEXTURES = os.path.join("assets", "textures")
REASON = 20  # a "why not" shorter than this says nothing
# "engine": the ENGINE cannot do the method itself, and that is said with its exact reason (`reason`: what Roblox
# lacks, and how that is known) - and the best stand-in IS built and held by the gate (`proof`). It is not "has" (the
# method itself is not there) and not "partly" (nothing of it is left to build): a closed row, said as what it is
STATES = ("has", "engine", "partly", "missing", "not_roblox")
WORD = {"has": "HAS", "engine": "STAND-IN", "partly": "PARTLY", "missing": "MISSING", "not_roblox": "NOT ROBLOX"}


def out(status, summary, next_action, **extra):
    print(json.dumps(dict({"schema": 1, "status": status, "summary": summary, "next_action": next_action}, **extra)))
    return 0 if status in ("pass", "warn") else 1


REFUSED = []  # the register's "refused" rules, as load() last read them (the gate reads them)


def load(path=REGISTER):
    """the register -> (its methods in the owner's order, {id: method}); a register that is not whole is an error"""
    doc = json.load(open(path, encoding="utf-8"))
    refused = doc.get("refused") if isinstance(doc.get("refused"), list) else []
    for rule in refused:
        if not (isinstance(rule, dict) and isinstance(rule.get("match"), dict) and isinstance(rule.get("says"), str) and rule["says"]):
            raise ValueError(f"{path}: a refused rule needs a match and what it says")
    REFUSED[:] = refused
    methods = doc.get("methods")
    if not isinstance(methods, list) or not methods:
        raise ValueError(f"{path}: no methods")
    by = {}
    for m in methods:
        if not isinstance(m, dict) or not isinstance(m.get("id"), str) or not isinstance(m.get("name"), str):
            raise ValueError(f"{path}: a method without an id and a name")
        if m["id"] in by:
            raise ValueError(f"{path}: two methods with the id {m['id']}")
        if m.get("state") not in STATES:
            raise ValueError(f"{path}: {m['id']}: state must be one of {', '.join(STATES)}")
        if m["state"] == "engine":
            if not (isinstance(m.get("reason"), str) and len(m["reason"].strip()) >= 20):
                raise ValueError(f"{path}: {m['id']}: an engine row says its reason (what Roblox lacks, and how that is known)")
            if not (isinstance(m.get("proof"), list) and m["proof"]):
                raise ValueError(f"{path}: {m['id']}: an engine row's stand-in is held by a proof - it has none")
        by[m["id"]] = m
    for m in methods:
        if m.get("stand_in") is not None and m["stand_in"] not in by:
            raise ValueError(f"{path}: {m['id']}: its stand-in {m['stand_in']} is not a method")
    # rows MADE FOR TESTS (not the owner's: never listed, never counted): a plan may name one, so that the refusal of
    # a method the kit lacks stays tested when none of the real ones is missing
    for m in doc.get("made_for_tests") or []:
        if isinstance(m, dict) and isinstance(m.get("id"), str) and m["id"].startswith("_") and m["id"] not in by and m.get("state") in STATES:
            by[m["id"]] = m
    return methods, by


def usable(m):
    return m["state"] in ("has", "engine", "partly")


# ("not a single shatter", "without any sign of smoke": the words between the denial and the cue are its own)
NOT_BEFORE = re.compile(r"(?:\bno|\bnot|\bwithout|\bnever|\bnor)(?:\s+(?:a|an|the|any|more|one|single|trace|sign|hint|of))*\s*$")
NOT_AFTER = re.compile(r"^\s+(?:is\s+|has\s+|are\s+|have\s+)?(?:gone|out|over|dead)\b")


def cue_hit(m, text):
    """the first of a method's cue words that the text holds, as a whole word (a plural counts), else None. A cue
    that the words deny is no hit: "no flame", "without smoke", "not a single shatter", "the fire gone" """
    low = text.lower()
    for cue in m.get("cues") or []:
        for hit in re.finditer(r"(?<![a-z-])" + re.escape(cue.lower()) + r"(?:s|es)?(?![a-z])", low):
            if NOT_BEFORE.search(low[:hit.start()]) or NOT_AFTER.search(low[hit.end():]):
                continue
            return cue
    return None


def find(methods, words):
    """methods ranked by how many of the words their name, their way, their cues and tools hold"""
    scored = []
    for m in methods:
        hay = " ".join([m["name"], m["id"].replace("_", " "), m.get("how", ""), " ".join(m.get("cues") or []),
                        " ".join(m.get("tools") or [])]).lower()
        name = (m["name"] + " " + m["id"].replace("_", " ")).lower()
        score = sum((3 if w in name else 1) for w in words if w in hay)
        if score:
            scored.append((-score, m["n"], m))
    return [m for _, _, m in sorted(scored, key=lambda s: s[:2])]


# ---------------------------------------------------------------------------------------------------------------
# the proof: what in a preset shows a method is used


def dig(obj, path):
    """a dotted path into a layer ("draw.cutSmear"); None when any step is missing"""
    for key in path.split("."):
        if not isinstance(obj, dict) or key not in obj:
            return None
        obj = obj[key]
    return obj


def numbers(v):
    """every number inside a value (a number, a curve of numbers or of [t, v] pairs, a table of such)"""
    if isinstance(v, bool):
        return []
    if isinstance(v, (int, float)):
        return [float(v)]
    if isinstance(v, dict):
        return [n for x in v.values() for n in numbers(x)]
    if isinstance(v, list):
        num = lambda x: isinstance(x, (int, float)) and not isinstance(x, bool)  # noqa: E731
        if v and all(isinstance(p, list) and len(p) == 2 and num(p[0]) for p in v):
            return [n for p in v for n in numbers(p[1])]  # [[t, value], ...] (a value may be a vector): the times are not values
        if len(v) >= 2 and all(isinstance(p, list) and len(p) == 3 and num(p[0]) and num(p[1]) and num(p[2]) for p in v) and v[0][0] == 0 and v[-1][0] == 1:
            return [float(p[1]) for p in v]  # [[t, value, envelope], ...] from 0 to 1: neither the times nor the envelopes are values
        return [n for x in v for n in numbers(x)]
    return []


def present(v):
    return v is not None and v is not False


def draws(layer):
    """does this layer put anything on screen? Not when it is fully transparent all its life, has no size, or no
    life: such a layer is in the preset and in nothing the owner sees, so it proves no method"""
    t = numbers(layer.get("transparency"))
    if t and min(t) >= 1:
        return False
    for key in ("size", "scale", "width", "range", "radius"):
        n = numbers(layer.get(key))
        if n and max(abs(x) for x in n) <= 0:
            return False
    for key in ("life", "lifetime"):
        n = numbers(layer.get(key))
        if n and max(n) <= 0:
            return False
    count, rate = numbers(layer.get("count")), numbers(layer.get("rate"))
    if layer.get("kind") in ("sprite", "debris", "swarm") and count and max(count) <= 0 and not (rate and max(rate) > 0):
        return False
    return True


def texture_keys(layer):
    """every texture a layer names: its own, its boil's, its lit and view variants"""
    keys = []
    for path in ("texture", "boil.texture", "dirtTexture"):
        v = dig(layer, path)
        if isinstance(v, str) and v:
            keys.append(v)
    for path in ("lit", "views"):
        v = dig(layer, path)
        if isinstance(v, dict):
            keys += [t for t in v.values() if isinstance(t, str) and t]
    return keys


class Specs:
    """texture specs by key, read once (<textures>/<key>.json; a key with no spec is None)"""

    def __init__(self, folder):
        self.folder, self.seen = folder, {}

    def get(self, key):
        if key not in self.seen:
            spec = None
            path = os.path.join(self.folder, f"{key}.json") if self.folder else ""
            if path and re.fullmatch(r"[A-Za-z0-9_.\-]+", key) and os.path.isfile(path):
                try:
                    spec = json.load(open(path, encoding="utf-8"))
                except (OSError, ValueError):
                    spec = None
            self.seen[key] = spec if isinstance(spec, dict) else None
        return self.seen[key]


def texture_proves(want, spec):
    if spec is None:
        return False
    recipe = spec.get("recipe")
    post = spec.get("post") if isinstance(spec.get("post"), dict) else {}
    if "recipe" in want and recipe not in want["recipe"]:
        return False
    if recipe == "comp" and isinstance(spec.get("comp"), dict) and spec["comp"].get("shock") is not None:
        try:   # a shock is proved by a spec the comp would bake (a loop, a graph beside it, an amount it refuses: never baked)
            here = os.path.dirname(os.path.abspath(__file__))
            if here not in sys.path:
                sys.path.insert(0, here)
            import comp
            comp.checked(spec)
        except (ValueError, TypeError, ImportError):
            return False
    if recipe == "liquid":   # a liquid sheet's spec is one kit vfx bakes (engine fx, a block the solver takes): anything else is never baked
        try:
            here = os.path.dirname(os.path.abspath(__file__))
            if here not in sys.path:
                sys.path.insert(0, here)
            import liquid
            liquid.checked(spec)
        except (ValueError, TypeError, ImportError):
            return False
    if "recipe_not" in want and (not isinstance(recipe, str) or recipe in want["recipe_not"]):
        return False
    def on(v):  # (a post step set to 0 or false is switched off)
        return present(v) and not (isinstance(v, (int, float)) and v == 0)

    if "post" in want and not all(on(post.get(k)) for k in want["post"]):
        return False
    if want.get("post_any") and not any(on(v) for v in post.values()):
        return False
    if "made_by" in want and want["made_by"] not in str(spec.get("about") or ""):
        return False
    for path, allowed in (want.get("where") or {}).items():  # a field of the spec itself ("dissolve.pattern")
        if dig(spec, path) not in allowed:
            return False
    for path in want.get("has") or []:  # a block the spec carries ("comp.warp")
        if not present(dig(spec, path)):
            return False
    for path in want.get("positive") or []:  # ... that DOES something ("comp.warp.amount" above 0)
        if not any(n > 0 for n in numbers(dig(spec, path))):
            return False
    for path in want.get("varies") or []:  # a ramp of more than one colour ("comp.ramp": [[position, [r, g, b]], ...])
        stops = dig(spec, path)
        colours = {json.dumps(s[1]) for s in stops if isinstance(s, list) and len(s) == 2} if isinstance(stops, list) else set()
        if len(colours) < 2:
            return False
    return True


def convex_once(points):
    """does the outline go round ONCE, turning one way only (a point on an edge is allowed: it turns 0)? A dent turns
    the other way, a bowtie or a star goes round other than once"""
    pts = [(float(q[0]), float(q[1])) for q in points]
    n = len(pts)
    size = max(max(abs(x) for x, _ in pts), max(abs(z) for _, z in pts), 1e-9)
    turns, total = [], 0.0
    for i in range(n):
        (ax, az), (bx, bz), (cx, cz) = pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
        e1, e2 = (bx - ax, bz - az), (cx - bx, cz - bz)
        if abs(e1[0]) + abs(e1[1]) < 1e-12 or abs(e2[0]) + abs(e2[1]) < 1e-12:
            return False   # (a point given twice)
        cr = e1[0] * e2[1] - e1[1] * e2[0]
        turns.append(cr)
        total += math.atan2(cr, e1[0] * e2[0] + e1[1] * e2[1])
    tol = 1e-6 * size * size
    one_way = all(t >= -tol for t in turns) or all(t <= tol for t in turns)
    return one_way and abs(abs(total) - 2 * math.pi) < 1e-6


def plan_flies(layer, key, effects):
    """a layer that flies a fracture plan (its `key` names it): the plan is THERE (<effects>/fractures/<name>.json,
    named as the game finds it), it has pieces, the layer's speed moves them, and the break reaches every piece
    before the layer's life is over (a piece whose turn never comes sits still, then is gone)"""
    name = layer.get(key)
    if not effects or not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        return False
    try:
        with open(os.path.join(effects, "fractures", f"{name}.json"), encoding="utf-8") as fh:
            pieces = json.load(fh).get("pieces")
        delays = [float(pc.get("delay") or 0) for pc in pieces]
        # every piece wide enough to be met (measured from its own points: a hand-edited plan's "width" may say anything)
        import sys
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:
            sys.path.insert(0, here)
        import fracture
        if any(len(pc.get("points") or []) < 3 or fracture.measure(pc["points"])[1] < fracture.MEET_WIDE
               or not convex_once(pc["points"]) for pc in pieces):
            # (and a piece with a DENT - its hull hid a thin arm - or one whose outline crosses itself: the pieces'
            # rule reads the points in their order)
            return False
    except (OSError, ValueError, TypeError, AttributeError, KeyError, IndexError, ImportError):
        return False
    speed, life = layer.get("speed"), layer.get("life", 1)
    if speed is not None and not (isinstance(speed, (int, float)) and not isinstance(speed, bool) and speed > 0):
        return False
    if not isinstance(life, (int, float)) or isinstance(life, bool):
        return False
    return len(delays) >= 2 and max(delays) < life


_RESTS = {}


def plan_rests(layer, key, effects):
    """a "rest" layer's pieces, FLOWN by the rule the game and the player run (kit/vfx/settle.py: each lands, slides,
    tips flat, lies on the floor or on a piece under it, and pieces that lie in each other part): with the layer's own
    life, gravity and speed every piece is at rest before the fade starts and no two lie in each other, at 30, 60 and
    144 frames a second. A `point` [x, y, z] lifts the slab y studs above the floor (it lands later); none sits ON the
    floor; a NAMED point, or one over 500 studs up, does not pass (the gate cannot fly it)"""
    name = layer.get(key)
    try:
        import sys
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:
            sys.path.insert(0, here)
        import settle
        path = os.path.join(effects, "fractures", f"{name}.json")
        st = os.stat(path)
        life, g, speed = layer.get("life", 1), layer.get("gravity", 120), layer.get("speed")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in (life, g)) or not (0.2 <= life and 1 <= g <= 2000):
            return False
        speed = float(speed) if isinstance(speed, (int, float)) and not isinstance(speed, bool) else None
        pt = layer.get("point")
        if isinstance(pt, str) or (isinstance(pt, list) and len(pt) == 3 and isinstance(pt[1], (int, float)) and pt[1] > 500):
            return False   # (a named point is not known here, and a slab that high is not flown: neither may pass as on the floor)
        height = float(pt[1]) if isinstance(pt, list) and len(pt) == 3 and isinstance(pt[1], (int, float)) and not isinstance(pt[1], bool) and pt[1] > 0 else 0.0
        k = (os.path.abspath(path), st.st_mtime_ns, st.st_size, float(life), float(g), speed, height)
        if k not in _RESTS:
            with open(path, encoding="utf-8") as fh:
                plan = json.load(fh)
            ok = True
            for fps in settle.RATES:
                rows, _ = settle.check(settle.fly(plan, min(float(life), 30.0), float(g), speed, fps, height), min(float(life), 30.0), pushed=speed != 0)
                ok = ok and all(c["ok"] for c in rows)
            _RESTS[k] = ok
        return _RESTS[k]
    except (OSError, ValueError, TypeError, KeyError, AttributeError, IndexError, ZeroDivisionError):
        return False


SIMS = {"cloth": "cloth", "soft": "soft", "sand": "sand", "hair": "hair", "geonodes": "geonodes", "water": "water"}  # a baked simulation's name -> the module beside this file that checks its bakes


def kept_file(layer, want, effects):
    """a layer that names a file the kit keeps beside the presets (want = {"key": "field.name", "dir": "fields"}): the
    name is as the game finds it and <effects>/<dir>/<name>.json is THERE (a misspelt name plays nothing)"""
    name = dig(layer, want.get("key", ""))
    if not effects or not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        return False
    path = os.path.join(effects, str(want.get("dir")), f"{name}.json")
    if not os.path.isfile(path):
        return False
    if want.get("dir") == "fields":
        # a field that is switched off, or a file that is not a field that moves the air, plays nothing
        gain = dig(layer, "field.gain")
        if gain is not None and not any(abs(n) >= 0.05 for n in numbers(gain)):
            return False
        import field as FIELD  # (kit/vfx/field.py: beside this file)
        try:
            with open(path, encoding="utf-8") as fh:
                made = FIELD.checked(json.load(fh))
            return all(c["ok"] for c in FIELD.check(made))
        except (OSError, ValueError, TypeError, KeyError, IndexError):
            return False
    if want.get("dir") == "points":
        # a point cloud: the file is a cloud that passes its checks, the layer's pull is not 0 all its life, and the
        # swarm has at least as many particles as half the cloud's points (fewer do not draw the shape)
        import points as POINTS  # (kit/vfx/points.py: beside this file)

        try:
            with open(path, encoding="utf-8") as fh:
                pts = POINTS.checked(json.load(fh))
        except (OSError, ValueError, TypeError):
            return False
        count, pull, size = layer.get("count", 40), dig(layer, "cloud.pull"), dig(layer, "cloud.size")
        if isinstance(count, bool) or not isinstance(count, (int, float)):
            return False
        if min(count, 40 if layer.get("shape") == "Rock" else 150) < len(pts):  # (the first half of a cloud's points is half a shape)
            return False
        if size is not None and (isinstance(size, bool) or not isinstance(size, (int, float)) or size < 0.5):  # (70 particles in a tenth of a stud)
            return False
        # the shape is SEEN: a particle is on its point after about 8 / pull seconds, so the pull over the layer's
        # life, and the peak pull over a particle's longest life, each come to 8 at least
        life, lifetime = layer.get("life", 1), layer.get("lifetime", 1)
        longest = max(numbers(lifetime) or [0.0])
        if isinstance(life, bool) or not isinstance(life, (int, float)) or life <= 0:
            return False
        steps = 200
        over = [POINTS.at_curve(pull, (k + 0.5) / steps, 8.0) for k in range(steps)]
        if sum(max(w, 0.0) for w in over) / steps * life < 8.0 or max(over) * longest < 8.0:
            return False
        return all(c["ok"] for c in POINTS.check(pts))
    if want.get("sim"):
        # a BAKED SIMULATION (want = {"key": "params.seq", "dir": "seq", "sim": "cloth"}): the file is that
        # simulation's bake and its own frames pass that simulation's checks (a billow is no cloth; a bake that hangs
        # still, stretches or jumps is refused); a layer that plays it round needs a bake whose ends meet
        import importlib

        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:
            sys.path.insert(0, here)
        fps = dig(layer, "params.fps")
        try:
            sim = importlib.import_module(SIMS[want["sim"]])  # (kit/vfx/<sim>.py: beside this file)
            with open(path, encoding="utf-8") as fh:
                made = json.load(fh)
            # a layer too short to show the bake proves nothing (a ball that has not landed yet, a sheet seen for two
            # frames): its life at its speed covers at least half the bake's frames
            life, shown = layer.get("life", 1), fps if isinstance(fps, (int, float)) and not isinstance(fps, bool) else 24
            if not isinstance(made, dict) or not isinstance(made.get("frames"), list) or isinstance(life, bool) or not isinstance(life, (int, float)):
                return False
            if life * shown < 0.5 * len(made["frames"]):
                return False
            # a bake's own origin is where its page says it is (the water at rest, the ground, the pin): the layer must
            # sit by it - centred on its first frame's box (the default) it sits somewhere else (stage 26)
            if layer.get("pivot") != "origin":
                return False
            # one module can bake more than one method (water: waves, shallow water): the bake's own recipe says which
            if want.get("recipes") and not (isinstance(made.get("args"), dict) and made["args"].get("recipe") in want["recipes"]):
                return False
            return isinstance(made, dict) and all(c["ok"] for c in sim.check(
                made, loop=dig(layer, "params.loop") is True, play=fps if isinstance(fps, (int, float)) and not isinstance(fps, bool) else 24))
        except (OSError, ValueError, TypeError, KeyError, IndexError, ImportError):
            return False
    return True


_REGISTRIES = {}


def baked(effects, key):
    """is a texture BAKED - packed by the kit's build, which registers it in the effects folder's _textures.json? A
    spec written by hand and never packed proved its methods (a review leftover of stage 25). Uploading it is a
    separate step and is not asked here. A folder with no registry (a test's made folder) is not asked"""
    if not effects:
        return True
    path = os.path.join(effects, "_textures.json")
    try:
        st = os.stat(path)
    except OSError:
        return True
    k = (os.path.abspath(path), st.st_mtime_ns, st.st_size)
    if k not in _REGISTRIES:
        try:
            with open(path, encoding="utf-8") as fh:
                reg = json.load(fh)
        except (OSError, ValueError):
            reg = {}
        _REGISTRIES[k] = reg if isinstance(reg, dict) else {}
    # (REGISTERED: the build writes an entry only for a sheet it packed. Whether it is UPLOADED - an id the game can
    # fetch - is another step, the owner's: an entry with no id plays its fallback in the game. The gate does not
    # ask that (35 registered textures used by 77 of the project's effects had no id on 2026-11-17: refusing them is
    # the owner's call, said on the audit page))
    return isinstance(_REGISTRIES[k].get(key), dict)


def layer_proves(alt, layer, specs, effects=None):
    """one alternative of a proof against ONE layer: every condition it names must hold on that layer"""
    if "kind" in alt and layer.get("kind") != alt["kind"]:
        return False
    for path in alt.get("has") or []:
        if not present(dig(layer, path)):
            return False
    for path, allowed in (alt.get("where") or {}).items():
        if dig(layer, path) not in allowed:
            return False
    for path in alt.get("lacks") or []:  # (a refused rule: the layer is WITHOUT what the game needs)
        if present(dig(layer, path)):
            return False
    for path, refused in (alt.get("where_not") or {}).items():
        if dig(layer, path) in refused:
            return False
    for path in alt.get("positive") or []:
        if not any(n > 0 for n in numbers(dig(layer, path))):
            return False
    for path in alt.get("zero") or []:
        if any(n != 0 for n in numbers(dig(layer, path))):
            return False
    for path in alt.get("nonzero") or []:  # a key that is there and does nothing (uvScroll [0, 0]) proves nothing
        if not any(n != 0 for n in numbers(dig(layer, path))):
            return False
    for path, want in (alt.get("least") or {}).items():  # MANY of a thing ({"count": {"min": 12, "default": 40}}: the default is the game's)
        got = dig(layer, path)
        plain = isinstance(got, (int, float)) and not isinstance(got, bool)
        if got is None or (want.get("else") == "default" and not plain):   # (what the game does not read as a number it takes its own default for)
            have = want.get("default", float("-inf"))
        else:
            have = max(numbers(got) or [float("-inf")])
        if have < want["min"]:
            return False
    if "texture" in alt and not any(texture_proves(alt["texture"], specs.get(k)) and baked(effects, k) for k in texture_keys(layer)):
        return False
    if "plan" in alt and not plan_flies(layer, alt["plan"], effects):
        return False
    if "rests" in alt and not plan_rests(layer, alt["rests"], effects):
        return False
    if "kept" in alt and not kept_file(layer, alt["kept"], effects):
        return False
    return any(k in alt for k in ("kind", "has", "lacks", "where", "where_not", "positive", "zero", "nonzero", "texture", "plan", "kept", "rests", "least"))


def proved(method, layers, specs, effects, set_name, beat=None):
    """is the method used by these layers (of that beat)? -> the alternative that proves it, or None. Only a layer
    that draws something counts"""
    alive = [layer for layer in layers if draws(layer)]
    for alt in method.get("proof") or []:
        if "layers_min" in alt:
            if len(alive) >= alt["layers_min"]:
                return alt
        elif "file" in alt:
            name = alt["file"].replace("{set}", glob.escape(set_name or ""))
            if "{beat}" in name and beat is None:
                continue
            name = name.replace("{beat}", glob.escape(str(beat)))
            if set_name and glob.glob(os.path.join(effects, name)):
                return alt
        elif any(layer_proves(alt, layer, specs, effects) for layer in alive):
            return alt
    return None


def say(alt):
    """one alternative in plain words"""
    if "layers_min" in alt:
        return f"{alt['layers_min']} layers or more"
    if "file" in alt:
        return f"a kept file {alt['file']}"
    bits = []
    if "texture" in alt:
        t = alt["texture"]
        if "recipe" in t:
            bits.append("a texture of recipe " + " / ".join(t["recipe"]))
        if "recipe_not" in t:
            bits.append("a texture the kit generated")
        if "post" in t:
            bits.append('a texture with "post": ' + " + ".join(t["post"]))
        if t.get("post_any"):
            bits.append('a texture with a "post" block')
        if "made_by" in t:
            bits.append(f"a texture made by {t['made_by']}")
        for path, allowed in (t.get("where") or {}).items():
            bits.append(f'a texture whose spec has "{path}": ' + " / ".join(json.dumps(a) for a in allowed))
        for path in t.get("has") or []:
            bits.append(f'a texture whose spec has a "{path}" block')
        for path in t.get("positive") or []:
            bits.append(f'a texture whose spec has "{path}" above 0')
        for path in t.get("varies") or []:
            bits.append(f'a texture whose "{path}" has more than one colour')
    if "kept" in alt and alt["kept"].get("sim"):
        which = f' --recipe {"|".join(alt["kept"]["recipes"])}' if alt["kept"].get("recipes") else ""
        bits.append(f'"{alt["kept"]["key"]}": a {alt["kept"]["sim"]} bake in assets/effects/{alt["kept"]["dir"]} that passes its checks '
                    f'(lune run kit vfx {alt["kept"]["sim"]} <name>{which}), played at half to twice its speed for at least half its frames, '
                    f'sitting by its own origin ("pivot": "origin")')
    elif "kept" in alt:
        bits.append(f'"{alt["kept"]["key"]}": a file that is there in assets/effects/{alt["kept"]["dir"]}')
    if "plan" in alt:
        bits.append(f'"{alt["plan"]}": a fracture plan that is there (kit vfx fracture), a speed above 0 and a life longer than the break takes to reach the last piece')
    for path, want in (alt.get("least") or {}).items():
        bits.append(f'"{path}" of {want["min"]} or more')
    if "rests" in alt:
        bits.append("a life in which every piece comes to rest before the fade (the last 15 %) with no two lying in each other, at 30, 60 and 144 frames a second "
                    f'(lune run kit vfx settle <plan> --life s says the life that does)')
    for path in alt.get("has") or []:
        bits.append(f'"{path}"')
    for path, allowed in (alt.get("where") or {}).items():
        bits.append(f'"{path}": ' + " / ".join(json.dumps(a) for a in allowed))
    for path, refused in (alt.get("where_not") or {}).items():
        bits.append(f'"{path}" other than ' + " / ".join(json.dumps(a) for a in refused))
    for path in alt.get("lacks") or []:
        bits.append(f'no "{path}"')
    for path in alt.get("positive") or []:
        bits.append(f'"{path}" above 0')
    for path in alt.get("zero") or []:
        bits.append(f'"{path}" at 0')
    for path in alt.get("nonzero") or []:
        bits.append(f'"{path}" that is not 0')
    kind = f"a{'n' if alt['kind'][0] in 'aeiou' else ''} {alt['kind']} layer" if "kind" in alt else "a layer"
    return kind + (" with " + ", ".join(bits) if bits else "")


def say_proof(method, most=3):
    alts = [say(a) for a in method.get("proof") or []]
    return " | ".join(alts[:most]) + (f" | ... ({len(alts) - most} more)" if len(alts) > most else "")


# ---------------------------------------------------------------------------------------------------------------
# the plan: a chart's beats and what each is made with


def beat_id(label):
    m = re.match(r"\s*(\d+)", str(label or ""))
    return m.group(1) if m else None


def ids_of(v):
    return [x for x in v if isinstance(x, str)] if isinstance(v, list) else []


def nots_of(v):
    return {k: w for k, w in v.items() if isinstance(k, str)} if isinstance(v, dict) else {}


def plan_of(chart):
    """{beat id: {"label", "methods": [ids], "not": {id: why}}} in the chart's order (rows with no number are left out)"""
    plan = {}
    for row in chart.get("beats") or []:
        if not isinstance(row, dict):
            continue
        b = beat_id(row.get("beat"))
        if b is None or b in plan:
            continue
        plan[b] = {"label": str(row.get("beat")), "methods": ids_of(row.get("methods")), "not": nots_of(row.get("not"))}
    return plan


def reason(why):
    """a reason as it is compared: its words, spaces evened out (anything that is not text is no reason)"""
    return " ".join(why.split()) if isinstance(why, str) else ""


def snapshot(chart):
    """the plan as the approval keeps it: {beat id: {"methods": sorted ids, "not": {id: the reason, word for word}}}
    (beats with neither left out)"""
    snap = {}
    for b, p in plan_of(chart).items():
        if p["methods"] or p["not"]:
            snap[b] = {"methods": sorted(set(p["methods"])), "not": {mid: reason(p["not"][mid]) for mid in sorted(p["not"])}}
    return snap


def owner_saw(chart):
    """the plan the OWNER approved ({} when he approved a chart with no plan), or None when the chart's approval is
    not his own (by "owner" exactly - chart.py writes anything else as "model-proposed") or there is none"""
    approved = chart.get("approved") if isinstance(chart.get("approved"), dict) else {}
    if str(approved.get("by") or "").strip().lower() != "owner" or not isinstance(approved.get("words"), str) or not approved["words"].strip():
        return None
    return approved.get("methods") if isinstance(approved.get("methods"), dict) else {}


def beat_words(beats_path):
    """{beat id: the beat sheet's words for WHAT IS ON SCREEN in it - its label and the cells of the columns that say
    what is seen and its shape (every cell when the sheet has no such column)}; {} when there is no sheet"""
    if not os.path.isfile(beats_path):
        return {}
    words, header = {}, None
    time = re.compile(r"^\s*([\d.]+)\s*(?:-\s*([\d.]+))?\s*s\s*$")
    for line in open(beats_path, encoding="utf-8"):
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if header is None and len(cells) >= 2 and not time.match(cells[1]):
            if not set("".join(cells)) <= set("-: "):
                header = cells
            continue
        if len(cells) >= 3 and time.match(cells[1]) and cells[2]:
            b = beat_id(cells[0])
            if b is not None and b not in words:
                seen = [i for i, h in enumerate(header or []) if i >= 2 and re.search(r"screen|vision|shape|seen", h, re.I)]
                keep = [0] + seen if seen else [i for i in range(len(cells)) if i != 1]
                words[b] = " ".join(cells[i] for i in keep if i < len(cells))
    return words


def good_reason(why):
    """a reason in words: text, REASON letters or more once a template's <...> is taken out, and more than one word
    (a run of one letter is not words)"""
    if not isinstance(why, str):
        return False
    text = re.sub(r"<[^>]*>", "", why).strip()
    return len(text) >= REASON and len(set(re.findall(r"[^\W\d_]{2,}", text.lower()))) >= 3


def plan_problems(by, plan, words, beats=None, set_name="<set>"):
    """what is wrong with the plan itself, for the beats named (default: all) -> [text]"""
    problems = []
    for b, p in plan.items():
        if beats is not None and b not in beats:
            continue
        label = re.sub(r"^\s*\d+\s*", "", p["label"]) or p["label"]
        if not p["methods"]:
            problems.append(f'beat {b} ("{label}") names no method: say which methods of the owner\'s list it is made with '
                            f"(lune run kit vfx methods --set {set_name} lists what its words call for)")
        for mid in p["methods"]:
            m = by.get(mid)
            if m is None:
                problems.append(f'beat {b}: "{mid}" is not a method of the list (lune run kit vfx methods <words> finds one)')
            elif m["state"] == "missing":
                problems.append(f'beat {b}: "{m["name"]}" is not built in the kit yet - plan what the kit has, or build the method first')
            elif m["state"] == "not_roblox":
                stand = by.get(m.get("stand_in") or "")
                problems.append(f'beat {b}: Roblox has no place for "{m["name"]}"'
                                + (f' - its stand-in is "{stand["name"]}" ({stand["id"]})' if stand else ""))
        for mid, why in p["not"].items():
            m = by.get(mid)
            if m is None:
                problems.append(f'beat {b}: "not" names "{mid}", which is not a method of the list')
            elif mid in p["methods"]:
                problems.append(f'beat {b}: "{m["name"]}" is both planned and left out')
            elif not good_reason(why):
                problems.append(f'beat {b}: leaving out "{m["name"]}" needs its reason in plain words ({REASON} letters or more, a sentence): the owner reads it on the chart')
        text = words.get(b, p["label"])
        for m in by.values():
            if not m.get("ask") or not usable(m) or m["id"] in p["methods"] or m["id"] in p["not"]:
                continue
            cue = cue_hit(m, text)
            if cue:
                tools = " + ".join(m.get("tools") or []) or "the kit's way"
                problems.append(f'beat {b} ("{label}") shows "{cue}", which the owner\'s list makes by "{m["name"]}" ({tools}): '
                                f'plan it ("methods": [..., "{m["id"]}"]), or say why not ("not": {{"{m["id"]}": "<why>"}}) - the chart shows the reason to him')
    return problems


def suggestions(methods, text):
    """the methods a beat's words call for: [(method, cue)] in the list's order"""
    hits = []
    for m in methods:
        cue = cue_hit(m, text)
        if cue:
            hits.append((m, cue))
    return hits


# ---------------------------------------------------------------------------------------------------------------
# the gate


TECHNIQUE = ("echo", "bursts", "flicker", "rim", "boil", "haze", "path", "onDeath", "lit")  # (VfxTech keys: gone once expanded)


def beat_tag(v, labels):
    """a layer's "beat" as a chart beat id: a whole number, a string of digits, or a beat's own label; else None"""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return str(int(v)) if float(v) == int(v) and v >= 0 else None
    if isinstance(v, str):
        t = v.strip()
        if re.fullmatch(r"\d+", t):
            return str(int(t))
        return labels.get(" ".join(t.split()).lower())
    return None


def playing(raw, expanded):
    """the layers that PLAY: the expanded preset's when there is one (a muted layer is gone from it, a part's layers
    are in it), each joined with the technique keys its own layer carried before expansion (rim, echo, ... exist only
    there); with no expansion, the preset's own layers"""
    own = [layer for layer in (raw.get("layers") if isinstance(raw, dict) and isinstance(raw.get("layers"), list) else []) if isinstance(layer, dict)]
    if not (isinstance(expanded, dict) and isinstance(expanded.get("layers"), list)):
        return own
    by_name = {}
    for layer in own:
        if isinstance(layer.get("name"), str):
            by_name.setdefault(layer["name"], layer)
    out = []
    for layer in expanded["layers"]:
        if not isinstance(layer, dict):
            continue
        before = by_name.get(layer.get("name")) if isinstance(layer.get("name"), str) else None
        if before is not None:
            layer = dict({k: before[k] for k in TECHNIQUE if k in before}, **layer)
        out.append(layer)
    return out


def refused_in(layers, specs):
    """what the GAME does not show (the register's "refused": measured engine facts), among the layers that play"""
    problems = []
    for rule in REFUSED:
        hit = [str(layer.get("name")) for layer in layers if draws(layer) and layer_proves(rule["match"], layer, specs)]
        if hit:
            problems.append(f"{len(hit)} layer(s) ({', '.join(hit[:3])}{' ...' if len(hit) > 3 else ''}): {rule['says']}")
    return problems


def gate(by, chart, words, raw, expanded, specs, effects, set_name, refused_only=False):
    """the method gate on one preset as it plays -> (problems, {beat: {"used": [ids], "said": [ids]}}).
    refused_only: the owner waived the method plan - only what the game does not show is still refused"""
    if refused_only:
        return refused_in(playing(raw, expanded), specs), {}
    plan = plan_of(chart)
    if not plan:
        return ["the chart has no numbered beats to plan methods on"], {}
    labels = {" ".join(p["label"].split()).lower(): b for b, p in plan.items()}
    layers = playing(raw, expanded)
    by_beat, odd, bare = {}, [], 0
    for layer in layers:
        if layer.get("beat") is None:
            bare += 1
            continue
        b = beat_tag(layer["beat"], labels)
        if b is None or b not in plan:
            odd.append(f'"{layer.get("name")}" says beat {json.dumps(layer["beat"])}')
        else:
            by_beat.setdefault(b, []).append(layer)
    problems = []
    tagged = bool(by_beat) or bool(odd)
    if odd:
        problems.append(f"{len(odd)} layer(s) name a beat the chart does not have ({'; '.join(odd[:3])}{' ...' if len(odd) > 3 else ''}): "
                        f"the chart's beats are {', '.join(plan)}")
    if tagged and not by_beat:
        problems.append("no layer builds a beat of the chart: nothing here can be held to its method plan")
        return problems, {}
    if tagged and bare:
        problems.append(f"{bare} layer(s) that play name no beat (a part's layers take theirs from its use: \"use\": [{{\"part\": ..., \"beat\": N}}]): "
                        f"they prove no method for any beat")
    # the beats this piece BUILDS: the ones its own layers name (what the scope check reads too), whether or not
    # those layers play - a beat whose every layer is muted is still a beat the piece says it builds
    claimed = set(by_beat)
    for layer in (raw.get("layers") if isinstance(raw, dict) and isinstance(raw.get("layers"), list) else []):
        if isinstance(layer, dict) and layer.get("beat") is not None:
            b = beat_tag(layer["beat"], labels)
            if b in plan:
                claimed.add(b)
    built = [b for b in plan if b in claimed] if tagged else list(plan)
    problems += plan_problems(by, plan, words, set(built), set_name)
    # a way of making something that the GAME does not show (the register's "refused": measured engine facts) is
    # refused on a new piece, whatever its plan says
    problems += refused_in(layers, specs)
    seen = owner_saw(chart)
    record = {}
    for b in built:
        p, mine = plan[b], (by_beat.get(b, []) if tagged else layers)
        used, said = [], []
        for mid in p["methods"]:
            m = by.get(mid)
            if m is None or not usable(m):
                continue
            if not m.get("proof"):
                said.append(mid)
            elif proved(m, mine, specs, effects, set_name, b):
                used.append(mid)
            else:
                problems.append(f'beat {b} plans "{m["name"]}" and nothing that plays in that beat uses it - it shows as: {say_proof(m)}. '
                                f"Use it, or change the plan where the owner reads it (the chart)")
        record[b] = {"used": used, "said": said}
        if seen is None:
            # (no approval of his own yet: the scene gate refuses the chart; a reason he could not have seen still
            # does not count, so say that once the chart is approved by anyone else)
            approved = chart.get("approved") if isinstance(chart.get("approved"), dict) else {}
            if approved.get("words"):
                for mid in p["not"]:
                    if mid in by and by[mid].get("ask") and good_reason(p["not"][mid]):
                        problems.append(f'beat {b}: leaving out "{by[mid]["name"]}" needs the OWNER\'s own approval of the chart that shows the reason '
                                        f'(this chart is approved by "{approved.get("by")}"): lune run kit vfx chart {set_name}, show him, '
                                        f'then --approve "<his words>" --by owner')
            continue
        was = seen.get(b) if isinstance(seen.get(b), dict) else {}
        for mid in ids_of(was.get("methods")):
            if mid not in p["methods"]:
                name = by[mid]["name"] if mid in by else mid
                problems.append(f'beat {b}: "{name}" was on the chart the owner approved and is gone from the plan: '
                                f"show him the chart again (lune run kit vfx chart {set_name}), his yes records the new plan")
        was_not = was.get("not") if isinstance(was.get("not"), dict) else {}
        for mid in p["not"]:
            if not (mid in by and by[mid].get("ask") and good_reason(p["not"][mid])):
                continue
            if mid not in was_not:
                problems.append(f'beat {b}: leaving out "{by[mid]["name"]}" is not on the chart the owner approved: '
                                f"draw it again (lune run kit vfx chart {set_name}) and show him - the reason counts once he has seen it")
            elif reason(was_not[mid]) != reason(p["not"][mid]):
                problems.append(f'beat {b}: the reason for leaving out "{by[mid]["name"]}" is not the one the owner read on the chart he approved: '
                                f"draw it again (lune run kit vfx chart {set_name}) and show him")
    return problems, record


def run_gate(opts):
    effects = opts.get("--effects", EFFECTS)
    name = opts.get("--name", "")
    try:
        _, by = load(opts.get("--register", REGISTER))
        raw = json.load(open(os.path.join(effects, f"{name}.json"), encoding="utf-8"))
        scene = raw.get("scene") if isinstance(raw, dict) else None
        set_name = scene.get("set") if isinstance(scene, dict) else None
        if not isinstance(set_name, str) or not set_name:
            print(json.dumps({"problems": [], "why": "no scene set"}))
            return 0
        measured = os.path.join(effects, "refs_measured")
        chart_path = os.path.join(measured, f"{set_name}.chart.json")
        only = bool(opts.get("--refused-only"))
        if not os.path.isfile(chart_path) and not only:
            print(json.dumps({"problems": [f"no method plan: there is no beat chart {chart_path.replace(os.sep, '/')} to hold it (lune run kit vfx chart {set_name}; "
                                           f"a piece whose chart the owner waived is let off its method plan the same way: kit approve vfx {name} \"<his words>\" --by owner --waive methods)"]}))
            return 0
        chart = json.load(open(chart_path, encoding="utf-8")) if os.path.isfile(chart_path) else {}
        chart = chart if isinstance(chart, dict) else {}
        words = beat_words(os.path.join(measured, f"{set_name}.beats.md"))
        specs = Specs(opts.get("--textures", TEXTURES))
        # the preset as it plays, and each of its variants as IT plays: "label=path" (the label empty for the preset)
        plays = []
        for item in opts.get("--expanded", []):
            label, _, path = item.partition("=") if "=" in item else ("", "", item)
            plays.append((label, json.load(open(path, encoding="utf-8"))))
        if not plays:
            plays = [("", None)]
        problems, record = [], {}
        for label, expanded in plays:
            got, rec = gate(by, chart, words, raw, expanded, specs, effects, set_name, only)
            for problem in got:
                text = f"variant {label}: {problem}" if label else problem
                if problem not in problems and text not in problems:
                    problems.append(text)
            record[label or "preset"] = rec
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        print(json.dumps({"problems": [f"the method gate could not read its files: {type(e).__name__}: {e}"]}))
        return 0
    print(json.dumps({"problems": problems, "beats": record.get("preset", next(iter(record.values()), {})), "plays": record}))
    return 0


# ---------------------------------------------------------------------------------------------------------------
# the commands


def show_list(methods, picked=None):
    rows = picked if picked is not None else methods
    lines = []
    for m in rows:
        line = f"{m['n']:>3}  {WORD[m['state']]:<10}  {m['name']}  [{m['id']}]"
        if m.get("ask"):
            line += "  (ASK)"
        lines.append(line)
        how = m.get("how", "")
        if picked is not None:
            if m.get("reason"):
                lines.append(f"       THE ENGINE: {m['reason']}")
            lines.append(f"       {how}")
            if m.get("tools"):
                lines.append("       tools: " + " ; ".join(m["tools"]))
            if usable(m) and m.get("proof"):
                lines.append("       shows in a preset as: " + say_proof(m, most=6))
            elif usable(m):
                lines.append("       cannot be measured in a preset: it is said, not checked")
            if m.get("stand_in"):
                lines.append(f"       its stand-in: {m['stand_in']}")
    return lines


def edit_plan(by, chart, opts):
    """--beat N --use a,b --not id="why" --drop id: one beat's plan changed in place -> problem text or None"""
    want = beat_id(opts["--beat"])
    row = next((r for r in chart.get("beats") or [] if isinstance(r, dict) and beat_id(r.get("beat")) == want), None)
    if want is None or row is None:
        return f"no beat {opts['--beat']} in the chart"
    methods, nots = ids_of(row.get("methods")), nots_of(row.get("not"))
    for mid in [x.strip() for x in opts.get("--use", "").split(",") if x.strip()]:
        if mid not in by:
            return f'"{mid}" is not a method of the list (lune run kit vfx methods <words> finds one)'
        if mid not in methods:
            methods.append(mid)
        nots.pop(mid, None)
    for item in opts.get("--not", []):
        mid, _, why = item.partition("=")
        mid = mid.strip()
        if mid not in by:
            return f'"{mid}" is not a method of the list'
        if not good_reason(why):
            return f'leaving out "{by[mid]["name"]}" needs its reason in plain words ({REASON} letters or more): --not {mid}="<why>"'
        nots[mid] = why.strip()
        if mid in methods:
            methods.remove(mid)
    for mid in [x.strip() for x in opts.get("--drop", "").split(",") if x.strip()]:
        if mid in methods:
            methods.remove(mid)
        nots.pop(mid, None)
    row["methods"] = methods
    if nots:
        row["not"] = nots
    else:
        row.pop("not", None)
    return None


def parse(argv):
    """flags with one value (--not may repeat), bare flags, and the words that are no flag"""
    opts, words, i = {}, [], 0
    bare = {"--gate", "--all", "--refused-only"}
    while i < len(argv):
        a = argv[i]
        if a in bare:
            opts[a] = True
        elif a.startswith("--"):
            if i + 1 >= len(argv):
                raise ValueError(f"{a} needs a value")
            if a in ("--not", "--expanded"):
                opts.setdefault(a, []).append(argv[i + 1])
            else:
                opts[a] = argv[i + 1]
            i += 1
        else:
            words.append(a)
        i += 1
    return opts, words


def _main(argv):
    opts, words = parse(argv)
    if opts.get("--gate"):
        return run_gate(opts)
    methods, by = load(opts.get("--register", REGISTER))
    effects = opts.get("--effects", EFFECTS)
    if "--set" in opts:
        set_name = opts["--set"]
        measured = os.path.join(effects, "refs_measured")
        chart_path = os.path.join(measured, f"{set_name}.chart.json")
        if not os.path.isfile(chart_path):
            return out("fail", f"methods {set_name}: no beat chart {chart_path.replace(os.sep, '/')} to hold the plan",
                       f"lune run kit vfx chart {set_name} (it needs the scene's beat sheet first)")
        chart = json.load(open(chart_path, encoding="utf-8"))
        if "--beat" in opts:
            problem = edit_plan(by, chart, opts)
            if problem:
                return out("fail", f"methods {set_name}: {problem}", "lune run kit vfx methods --set " + set_name)
            json.dump(chart, open(chart_path, "w", encoding="utf-8", newline="\n"), indent=1)
        words_by = beat_words(os.path.join(measured, f"{set_name}.beats.md"))
        plan = plan_of(chart)
        problems = plan_problems(by, plan, words_by, None, set_name)
        for b, p in plan.items():
            print(f"beat {p['label']}")
            print("   made with: " + (", ".join(f"{by[m]['name']} [{m}]" if m in by else f"?? [{m}]" for m in p["methods"]) or "(nothing planned)"))
            for mid, why in p["not"].items():
                print(f"   NOT {by[mid]['name'] if mid in by else mid}: {why}")
            hits = [(m, cue) for m, cue in suggestions(methods, words_by.get(b, p["label"])) if m["id"] not in p["methods"] and m["id"] not in p["not"]]
            for m, cue in hits:
                tag = "ASK " if m.get("ask") and usable(m) else ""
                print(f'   its words say "{cue}": {tag}{m["name"]} [{m["id"]}] - {WORD[m["state"]]}')
        for problem in problems:
            print("OPEN: " + problem)
        edited = "written; " if "--beat" in opts else ""
        if problems:
            return out("fail", f"methods {set_name}: {edited}{len(problems)} thing(s) open in the plan of {len(plan)} beat(s)",
                       f'plan each beat: lune run kit vfx methods --set {set_name} --beat N --use id,id [--not id="why"]; then draw the chart again',
                       open=problems)
        return out("pass", f"methods {set_name}: {edited}every one of {len(plan)} beat(s) has its plan",
                   f"draw the chart so the owner reads the plan with it: lune run kit vfx chart {set_name}")
    if words:
        picked = find(methods, [w.lower() for w in words])
        if not picked:
            return out("fail", f'methods: nothing in the list matches "{" ".join(words)}"', "lune run kit vfx methods (the whole list)")
        print("\n".join(show_list(methods, picked[:8])))
        return out("pass", f'methods: {len(picked)} match(es) for "{" ".join(words)}"' + (", the best 8 shown" if len(picked) > 8 else ""),
                   'plan a beat with one: lune run kit vfx methods --set <set> --beat N --use <id>')
    print("\n".join(show_list(methods)))
    count = {s: sum(1 for m in methods if m["state"] == s) for s in STATES}
    return out("pass", f"methods: {len(methods)} of the owner's list - {count['has']} the kit has, {count['engine']} the engine cannot "
               f"and a stand-in is held, {count['partly']} partly, {count['missing']} missing, {count['not_roblox']} Roblox has no place for",
               "lune run kit vfx methods <words> (one method: how, its tool, what proves it) ; lune run kit vfx methods --set <set> (a scene's plan)",
               counts=count)


def main(argv):
    try:
        return _main(argv)
    except (OSError, ValueError, KeyError, TypeError) as e:
        return out("fail", f"methods: {type(e).__name__}: {e}", "lune run kit vfx methods (the list) ; --set <set> (a scene's plan)")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv[1:]))
