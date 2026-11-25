"""fit.py — fit an effect's COLOURS to its references with no hands: every colour in the preset (layer colours and
colour sequences, highlight fill/outline, lights) is graded by a saturation push and a brightness gain; each grade is
written as a temporary preset, recorded headless (autorec.py) and scored (refkit.py compare); the best grade is kept
under a NEW name (<effect>_fit by default — the original is never touched).

    python kit/vfx/fit.py <effect> <refs set> [--as <new>] [--views hero] [--sat 0.8,1,1.25,1.6,2] [--gain 0.85,1,1.15]
                                            [--times 0.9,1.2]   (the moments to judge: a SHORT effect needs them)

Why: measured reference colours are what the frame SHOWS; additive layers stack and wash out (or burn), so the input
colours that land on the target differ per effect — searching beats guessing (Saiyan forms: hand guesses missed by
2-17 points). Prints one JSON line with every grade's score.
"""

import copy
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FX = os.path.join("assets", "effects")


def grade_rgb(c, sat, gain):
    g = sum(c) / 3
    return [int(max(0, min(255, round((g + (x - g) * sat) * gain)))) for x in c]


def is_rgb(v):
    return isinstance(v, list) and len(v) == 3 and all(isinstance(x, (int, float)) for x in v)


def grade_value(v, sat, gain):
    if is_rgb(v):
        return grade_rgb(v, sat, gain)
    if isinstance(v, list) and v and all(isinstance(k, list) and len(k) == 2 and is_rgb(k[1]) for k in v):  # [[t, rgb], ...]
        return [[k[0], grade_rgb(k[1], sat, gain)] for k in v]
    return v


def graded(preset, sat, gain):
    p = copy.deepcopy(preset)
    for el in p.get("layers", []):
        for key in ("color", "fill", "outline", "tint"):
            if key in el:
                el[key] = grade_value(el[key], sat, gain)
    return p


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    line = next((ln for ln in reversed(r.stdout.splitlines()) if ln.startswith("{")), "{}")
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return {}


def score(name, refs, views, times=None):
    cmd = [sys.executable, "-I", os.path.join(HERE, "autorec.py"), name, "--views", views, "--compare", refs]
    if times:
        cmd += ["--times", times]
    rec = run(cmd)
    res = (rec.get("results") or [{}])[0]
    return (res.get("compare") or {}).get("score"), res


def main(argv):
    if len(argv) < 2:
        print(json.dumps({"schema": 1, "status": "fail", "summary": "fit: needs <effect> <refs set>", "next_action": "python kit/vfx/fit.py <effect> <set>"}))
        return 2
    effect, refs, opts, i = argv[0], argv[1], {}, 2
    while i < len(argv) - 1:
        opts[argv[i]] = argv[i + 1]
        i += 2
    new = opts.get("--as", f"{effect}_fit")
    if new == effect:
        print(json.dumps({"schema": 1, "status": "fail", "summary": "fit: --as must be a NEW name (the original is never touched)", "next_action": "--as <new>"}))
        return 2
    views = opts.get("--views", "hero")
    sats = [float(x) for x in opts.get("--sat", "0.8,1,1.25,1.6,2").split(",")]
    gains = [float(x) for x in opts.get("--gain", "0.85,1,1.15").split(",")]
    src = json.load(open(os.path.join(FX, f"{effect}.json"), encoding="utf-8"))
    tmp = f"_fit_{effect}"[:80]
    tmp_path = os.path.join(FX, f"{tmp}.json")
    tried = []

    def trial(sat, gain):
        json.dump(graded(src, sat, gain), open(tmp_path, "w", encoding="utf-8", newline="\n"), indent=1)
        sc, _ = score(tmp, refs, views, opts.get("--times"))
        tried.append({"sat": sat, "gain": gain, "score": sc})
        return sc if sc is not None else -1

    def val(sc):
        return sc if sc is not None else -1

    try:
        best_sat = max(sats, key=lambda s: trial(s, 1.0))  # saturation first (the big lever), then brightness
        best_gain = max(gains, key=lambda g: trial(best_sat, g) if g != 1.0 else val(next(t["score"] for t in tried if t["sat"] == best_sat and t["gain"] == 1.0)))
    finally:
        if os.path.isfile(tmp_path):
            os.remove(tmp_path)
    if all(t["score"] is None for t in tried):  # nothing could be scored: write nothing, say so
        print(json.dumps({"schema": 1, "status": "fail", "summary": f"fit {effect}: no grade could be scored (recording or compare failed every time)",
                          "next_action": "run python kit/vfx/autorec.py on it alone and read results[].why; a short effect needs --times", "tried": tried}))
        return 1
    best = max(tried, key=lambda t: val(t["score"]))
    base = next((t["score"] for t in tried if t["sat"] == 1.0 and t["gain"] == 1.0), None)
    out = graded(src, best["sat"], best["gain"])
    out["about"] = f"{effect} colour-fitted to {refs} (sat x{best['sat']}, gain x{best['gain']}: {base} -> {best['score']}) — kit/vfx/fit.py. " + src.get("about", "")
    json.dump(out, open(os.path.join(FX, f"{new}.json"), "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps({"schema": 1, "status": "pass", "summary": f"fit {effect} -> {new}: best sat x{best['sat']} gain x{best['gain']} scores {best['score']} (as built: {base}); {len(tried)} grades tried",
                      "next_action": f"python kit/vfx/autorec.py {new} (all views), LOOK, then keep it only if it reads better than {effect}", "tried": tried}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
