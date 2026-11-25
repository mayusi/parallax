"""match.py — fit a recipe's NUMBERS to a reference sound by its measured ears (measure, don't guess).

Usage: python kit/audio/match.py <name> --to <file|name> [--evals 600] [--range 4] [--write] [--recipes DIR]
       (normally: lune run kit sfx match <name> --to <ref>)
Tunes every continuous number of assets/sounds/<name>.json — layer gains, envelope attack/decay/release, filter
cutoffs (each end of a glide), oscillator frequencies (each end), layer delays, fx reverb — within a factor of
--range of where they are (log scale), with CMA-ES (kit/blender/cmaes.py), to minimise ears.distance between the
render and the reference. The SHAPE of the recipe (which layers, which sources) is the designer's; the numbers
are fitted. Writes assets/sounds/<name>.matched.json (with --write: replaces the recipe, the old one kept as
<name>.pre-match.json), renders build/sounds/matched/<name>.ogg and its sheet beside the reference.
Prints one JSON verdict line: distance before -> after and the differences that remain, in words.
"""

import contextlib
import copy
import io
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "blender"))
import ears as E  # noqa: E402
import synth  # noqa: E402
from cmaes import CMAES  # noqa: E402

RECIPES = os.path.join("assets", "sounds")


def knobs(recipe):
    """Every tunable number as (getter path, initial value, kind). kind: 'log' (a factor), 'lin' (seconds)."""
    out = []
    for li, layer in enumerate(recipe["layers"]):
        out.append(((li, "gain"), float(layer.get("gain", 1.0)), "gain"))
        env = layer.get("env")
        if isinstance(env, dict):
            for k in ("attack", "decay", "release"):
                if k in env and float(env[k]) > 0:
                    out.append(((li, "env", k), float(env[k]), "log"))
        filt = layer.get("filter")
        if isinstance(filt, dict) and "cutoff" in filt:
            c = filt["cutoff"]
            if isinstance(c, (list, tuple)):
                out += [((li, "filter", "cutoff", j), float(c[j]), "log") for j in range(len(c))]
            else:
                out.append(((li, "filter", "cutoff"), float(c), "log"))
        f = layer.get("freq")
        if f is not None and layer.get("source", "sine") not in ("noise", "click", "sample", "modal"):
            if isinstance(f, (list, tuple)):
                out += [((li, "freq", j), float(f[j]), "log") for j in range(len(f))]
            else:
                out.append(((li, "freq"), float(f), "log"))
        if float(layer.get("delay", 0)) > 0:
            out.append(((li, "delay"), float(layer["delay"]), "log"))
    if float(recipe.get("fx", {}).get("reverb", 0)) > 0:
        out.append((("fx", "reverb"), float(recipe["fx"]["reverb"]), "log"))
    return out


def apply(recipe, ks, x):
    r = copy.deepcopy(recipe)
    for (path, v0, _), xi in zip(ks, x):
        v = v0 * math.exp(xi)
        if path[0] == "fx":
            r["fx"]["reverb"] = min(1.0, v)
            continue
        node = r["layers"][path[0]]
        for p in path[1:-1]:
            node = node[p]
        last = path[-1]
        if path[1] == "filter":
            v = min(v, synth.SR * 0.45)
        if path[1] == "env" and last == "attack":
            v = max(v, 0.0001)
        node[last] = v
    return r


def render_ears(recipe):
    x = synth.render(recipe, seed=1000, pitch=1.0)
    return E.measure(x, synth.SR, loop=recipe.get("loop", False)), x


# which layer ROLE answers for which measure (the first role the recipe has wins), and the knob that moves it
ROLE_OF = {
    "sub_share": ("sub", "body"),
    "high_share": ("air", "sweetener", "body"),
    "brightness_hz": ("body", "air", "transient"),
    "tail_ms": ("tail", "body"),
    "transient_ms": ("transient", "body"),
    "attack_ms": ("transient", "body"),
    "crest_db": ("transient", "body"),
    "flux": ("mechanical", "body", "air"),
}
SCALE = {"sub_share": 0.05, "high_share": 0.06, "brightness_hz": None, "tail_ms": 80, "transient_ms": 3,
         "attack_ms": 4, "crest_db": 2, "lufs": 1.5, "flux": 1.5}


def _layer_label(recipe, i):
    layer = recipe["layers"][i]
    return f"layer {i + 1} ({layer.get('role', '?')}, {layer.get('source', '?')})"


def roles_report(recipe, after, target):
    """What is still different, said PER ROLE, and ONE edit: the biggest remaining difference turned into a knob on
    the layer that owns it (verifier over judge: a difference + an edit, never a score)."""
    d, words = E.delta(after, target)
    layers = recipe.get("layers") or []
    have = {}
    for i, layer in enumerate(layers):
        have.setdefault(layer.get("role") or "body", i)
    by_role, worst = {}, None
    for k, scale in SCALE.items():
        if k not in d:
            continue
        if k == "brightness_hz":
            size = abs(d[k]) / max(abs(target.get(k, 1.0)), 1e-9) / 0.10
        else:
            size = abs(d[k]) / scale
        if size < 1:
            continue
        owner = "mix" if k == "lufs" else next((r for r in ROLE_OF.get(k, ()) if r in have), None)
        if owner is None:
            owner = "missing:" + ROLE_OF[k][0]
        by_role.setdefault(owner, []).append((size, k, d[k]))
        if worst is None or size > worst[0]:
            worst = (size, k, d[k], owner)
    roles = {}
    for role, items in by_role.items():
        items.sort(key=lambda t: -t[0])
        roles[role] = [_measure_words(k, v, target) for _, k, v in items]
    for role in have:
        roles.setdefault(role, ["matches the reference"])
    edit = None
    if worst:
        _, k, v, owner = worst
        edit = _one_edit(recipe, have, owner, k, v, target)
    return roles, edit, words


def _measure_words(k, v, target):
    if k == "brightness_hz":
        return f"{abs(v) / max(abs(target.get(k, 1.0)), 1e-9) * 100:.0f} % {'brighter' if v > 0 else 'darker'}"
    unit = {"tail_ms": " ms", "transient_ms": " ms", "attack_ms": " ms", "crest_db": " dB crest", "lufs": " LU"}.get(k, "")
    if k in ("sub_share", "high_share"):
        return f"{'more' if v > 0 else 'less'} {'sub' if k == 'sub_share' else 'air'} ({abs(v) * 100:.0f} pts)"
    return f"{k.replace('_ms', '').replace('_db', '').replace('_', ' ')} {'+' if v > 0 else '-'}{abs(v):.1f}{unit}"


def _one_edit(recipe, have, owner, k, v, target):
    """the single most useful knob change, in the recipe's own terms"""
    if owner == "mix":
        return f"fx.loudness {'-' if v > 0 else '+'}{abs(v):.1f} LU (the whole sound is {abs(v):.1f} LU {'louder' if v > 0 else 'quieter'})"
    if owner.startswith("missing:"):
        return f"add a '{owner.split(':', 1)[1]}' layer: no layer of that role exists to fix '{k}'"
    i = have[owner]
    label = _layer_label(recipe, i)
    layer = recipe["layers"][i]
    if k in ("sub_share", "high_share"):
        db = max(-9.0, min(9.0, -v / (0.05 if k == "sub_share" else 0.06) * 2.0))
        return f"{label}: gain {db:+.1f} dB"
    if k == "brightness_hz":
        cut = (layer.get("filter") or {}).get("cutoff")
        cut = cut[-1] if isinstance(cut, list) else cut
        ratio = target.get(k, 1.0) / max(target.get(k, 1.0) + v, 1e-9)
        if isinstance(cut, (int, float)):
            return f"{label}: filter cutoff {cut:.0f} -> {cut * ratio:.0f} Hz"
        return f"{label}: add a lowpass at {target.get(k, 2000) * 2:.0f} Hz" if v > 0 else f"{label}: more drive or a brighter source (it is {abs(v):.0f} Hz darker)"
    if k == "tail_ms":
        rel = (layer.get("env") or {}).get("release") or (layer.get("env") or {}).get("decay")
        if isinstance(rel, (int, float)) and rel > 0:
            return f"{label}: env release {rel:.3f} -> {max(0.005, rel - v / 1000):.3f} s"
        return f"{label}: {'shorten' if v > 0 else 'lengthen'} its envelope by {abs(v):.0f} ms"
    if k in ("transient_ms", "attack_ms", "crest_db"):
        sharpen = (v > 0) if k != "crest_db" else (v < 0)
        return f"{label}: transient shaper attack {'+3' if sharpen else '-3'} dB ({'sharper' if sharpen else 'softer'} hit)"
    if k == "flux":
        return f"{label}: {'smoother (less noise / drive)' if v > 0 else 'grainier (more noise / drive)'}"
    return f"{label}: adjust for {k}"


def main(argv):
    name, ref, evals, rng_factor, write, recipes = None, None, 600, 4.0, False, RECIPES
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--to", "--evals", "--range", "--recipes"):
            v = argv[i + 1]
            if a == "--to":
                ref = v
            elif a == "--evals":
                evals = int(v)
            elif a == "--range":
                rng_factor = float(v)
            else:
                recipes = v
            i += 2
            continue
        if a == "--write":
            write = True
        else:
            name = a
        i += 1
    path = os.path.join(recipes, f"{name}.json") if name else ""
    if not name or not os.path.isfile(path):
        print(json.dumps({"status": "fail", "summary": f"no recipe {path}", "next_action": "lune run kit sfx match <name> --to <file|name> (the recipe must exist: kit new sound <name>)"}))
        return 1
    if not ref:
        print(json.dumps({"status": "fail", "summary": "no reference", "next_action": f"lune run kit sfx match {name} --to <file|name>"}))
        return 1
    if not os.path.isfile(ref):
        cand = os.path.join("build", "sounds", f"{ref}.ogg")
        if not os.path.isfile(cand):
            print(json.dumps({"status": "fail", "summary": f"no reference {ref}", "next_action": "pass a sound file or a rendered sound name"}))
            return 1
        ref = cand
    with open(path, encoding="utf-8") as fh:
        recipe = json.load(fh)
    target = E.measure(E.decode(ref)[0], synth.SR, loop=recipe.get("loop", False))
    ks = knobs(recipe)
    if not ks:
        print(json.dumps({"status": "fail", "summary": "nothing numeric to tune", "next_action": "give the layers gains / envelopes / filters"}))
        return 1
    before_ears, _ = render_ears(recipe)
    before = E.distance(before_ears, target)
    r = math.log(rng_factor)
    lo = [-(r * 2 if k == "gain" else r) for _, _, k in ks]
    hi = [(r * 2 if k == "gain" else r) for _, _, k in ks]
    es = CMAES(x0=[0.0] * len(ks), sigma=r / 2, lo=lo, hi=hi, seed=1, max_evals=evals)
    best_x, best_f = np.zeros(len(ks)), before
    with contextlib.redirect_stdout(io.StringIO()):
        while not es.done():
            xs = es.ask()
            fs = []
            for x in xs:
                try:
                    f = E.distance(render_ears(apply(recipe, ks, x))[0], target)
                except (ValueError, FloatingPointError):
                    f = 1e6
                fs.append(f)
                if f < best_f:
                    best_f, best_x = f, np.array(x)
            es.tell(xs, fs)
    matched = apply(recipe, ks, best_x)
    for layer in matched["layers"]:  # readable numbers in the file
        for k, v in list(layer.items()):
            if isinstance(v, float):
                layer[k] = round(v, 5)
        for sub in ("env", "filter"):
            if isinstance(layer.get(sub), dict):
                for k, v in list(layer[sub].items()):
                    if isinstance(v, float):
                        layer[sub][k] = round(v, 5)
                    elif isinstance(v, list):
                        layer[sub][k] = [round(float(e), 3) for e in v]
        if isinstance(layer.get("freq"), list):
            layer["freq"] = [round(float(e), 3) for e in layer["freq"]]
    matched["_matched"] = {"to": ref.replace("\\", "/"), "distance_before": round(before, 2), "distance_after": round(best_f, 2), "evals": es.evals if hasattr(es, "evals") else evals}
    out_json = os.path.join(recipes, f"{name}.matched.json")
    if write:
        os.replace(path, os.path.join(recipes, f"{name}.pre-match.json"))
        out_json = path
    with open(out_json, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(matched, fh, indent=1)
    after_ears, x = render_ears(matched)
    out_dir = os.path.join("build", "sounds", "matched")
    os.makedirs(out_dir, exist_ok=True)
    ogg = os.path.join(out_dir, f"{name}.ogg")
    synth.write_ogg(x, ogg)
    roles, edit, words = roles_report(matched, after_ears, target)
    import sheet

    with contextlib.redirect_stdout(io.StringIO()):
        sheet.draw(name, [ogg], os.path.join(out_dir, "sheets"), ref)
    gain = (before - best_f) / max(before, 1e-9)
    print(json.dumps({
        "status": "pass",
        "summary": f"{name}: distance {before:.2f} -> {best_f:.2f} ({gain * 100:.0f} % closer) over {len(ks)} numbers; written {out_json.replace(os.sep, '/')}",
        "next_action": (f"ONE edit: {edit}; then lune run kit sfx listen {name} --ref {ref}" if edit
                        else f"listen to {ogg.replace(os.sep, '/')} beside the reference"),
        "distance_before": round(before, 3),
        "distance_after": round(best_f, 3),
        "remaining": words,
        "roles": roles,
        "edit": edit,
        "recipe": out_json.replace(os.sep, "/"),
        "render": ogg.replace(os.sep, "/"),
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
