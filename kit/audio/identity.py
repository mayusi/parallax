"""identity.py — a game's SONIC IDENTITY: every sound of one game should come from one world (the UI lane's identity
idea, for sound). assets/sounds/identities/<id>.json:
{ "about": "anime battlegrounds: punchy, bright, dry",
  "classes": {                                  measured ranges per class (a set member's "class", else "default")
    "hit":   { "lufs": [-18, -13], "crest_db": [12, 26], "brightness_hz": [400, 2600], "tail_ms": [120, 1400] },
    "swing": { "lufs": [-22, -16], "brightness_hz": [1500, 9000], "tail_ms": [80, 400] },
    "default": { "lufs": [-24, -10] } },
  "bans": [ { "source": "square", "why": "chiptune squares do not belong in an anime fight" } ] }

Usage: python kit/audio/identity.py <id> --check <sound|set ...>     gate sounds against the identity
       python kit/audio/identity.py <id> --from <file ...> [--class hit]   derive (or add) a class's ranges from
                                                                         reference recordings (p10..p90, widened)
       (normally: lune run kit sfx identity <id> ...)
A sound outside a range is a WARNING ("improve: <name> is 30 % brighter than the identity's hits"); a banned source in
a recipe is an ERROR. Prints one JSON verdict line.
"""

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ears as E  # noqa: E402

IDS = os.path.join("assets", "sounds", "identities")
SOUNDS, RECIPES = os.path.join("build", "sounds"), os.path.join("assets", "sounds")
KEYS = ("lufs", "crest_db", "brightness_hz", "tail_ms", "transient_ms", "sub_share", "high_share")


def load(identity):
    p = os.path.join(IDS, f"{identity}.json")
    if not os.path.isfile(p):
        return None, p
    with open(p, encoding="utf-8") as fh:
        return json.load(fh), p


def members(names):
    """sound name -> (recipe layers, class) for plain names and for whole sets."""
    out = {}
    import sets as S

    for n in names:
        sp = os.path.join(RECIPES, "sets", f"{n}.json")
        if os.path.isfile(sp):
            with open(sp, encoding="utf-8") as fh:
                for sname, r in S.resolve(json.load(fh)).items():
                    out[sname] = (r["layers"], r.get("_class", "default"))
            continue
        rp = os.path.join(RECIPES, f"{n}.json")
        layers, cls = [], "default"
        if os.path.isfile(rp):
            with open(rp, encoding="utf-8") as fh:
                r = json.load(fh)
            layers, cls = r.get("layers", []), r.get("class", "default")
        out[n] = (layers, cls)
    return out


def check(identity, names):
    ident, path = load(identity)
    if ident is None:
        return {"status": "fail", "summary": f"no identity {path}", "next_action": f"write it (shape: top of kit/audio/identity.py) or derive it: lune run kit sfx identity {identity} --from <refs ...> --class hit"}
    errors, warns, checked = [], [], 0
    classes = ident.get("classes", {})
    for name, (layers, cls) in members(names).items():
        for i, layer in enumerate(layers):
            src = "sample" if "sample" in layer else layer.get("source", "sine")
            for ban in ident.get("bans", []):
                if ban.get("source") == src:
                    errors.append(f"{name} layer {i + 1}: {src} is banned in {identity} ({ban.get('why', '')})")
        f = os.path.join(SOUNDS, f"{name}.ogg")
        if not os.path.isfile(f):
            warns.append(f"{name}: not rendered (kit sfx {name} / kit sfx set)")
            continue
        e = E.measure(E.decode(f)[0])
        checked += 1
        rng = dict(classes.get("default", {}))
        rng.update(classes.get(cls, {}))
        for k, (lo, hi) in rng.items():
            v = e.get(k)
            if v is None:
                continue
            if v < lo or v > hi:
                side = "below" if v < lo else "above"
                warns.append(f"improve: {name} ({cls}) {k} {v} is {side} {identity}'s {lo}..{hi}")
    status = "fail" if errors else "pass"
    return {"status": status,
            "summary": f"{checked} sound(s) against {identity}: {len(errors)} banned layer(s), {len(warns)} outside the identity" + (f" — {errors[0]}" if errors else ""),
            "next_action": errors[0] if errors else (warns[0] if warns else "none — proceed"),
            "errors": errors, "warnings": warns}


def derive(identity, files, cls):
    es = []
    for f in files:
        p = f if os.path.isfile(f) else os.path.join(SOUNDS, f"{f}.ogg")
        if os.path.isfile(p):
            es.append(E.measure(E.decode(p)[0]))
    if len(es) < 2:
        return {"status": "fail", "summary": "need 2+ reference recordings to derive a range", "next_action": "pass more files (kit sfx find gives library paths)"}
    ident, path = load(identity)
    ident = ident or {"about": f"derived from {len(es)} reference(s)", "classes": {}, "bans": []}
    rng = {}
    for k in KEYS:
        vals = np.array([e[k] for e in es], float)
        lo, hi = np.percentile(vals, 10), np.percentile(vals, 90)
        pad = max((hi - lo) * 0.1, abs(hi) * 0.05, 1e-3)
        rng[k] = [round(float(lo - pad), 3), round(float(hi + pad), 3)]
    ident.setdefault("classes", {})[cls] = rng
    os.makedirs(IDS, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(ident, fh, indent=1)
    return {"status": "pass", "summary": f"{identity}.{cls} derived from {len(es)} reference(s): " + ", ".join(f"{k} {v[0]}..{v[1]}" for k, v in list(rng.items())[:4]),
            "next_action": f"check sounds against it: lune run kit sfx identity {identity} --check <sound|set ...>", "file": path.replace(os.sep, "/")}


def main(argv):
    if not argv:
        print(json.dumps({"status": "fail", "summary": "usage: identity.py <id> --check <names> | --from <files> --class <c>", "next_action": "lune run kit sfx identity <id> --check <set>"}))
        return 1
    identity, rest = argv[0], argv[1:]
    if "--from" in rest:
        i = rest.index("--from")
        files = [a for a in rest[i + 1 :] if not a.startswith("--")]
        cls = rest[rest.index("--class") + 1] if "--class" in rest else "default"
        files = [f for f in files if f != cls]
        r = derive(identity, files, cls)
    else:
        names = [a for a in rest if not a.startswith("--")]
        if not names:
            r = {"status": "fail", "summary": "nothing to check", "next_action": f"lune run kit sfx identity {identity} --check <sound|set ...>"}
        else:
            r = check(identity, names)
    for e in r.get("errors", []):
        print("  ERROR " + e)
    for w in r.get("warnings", [])[:12]:
        print("  warn  " + w)
    print(json.dumps(r))
    return 0 if r["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
