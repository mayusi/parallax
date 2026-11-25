"""fuzz.py — a screen under EDGE DATA (what QA throws at a menu before players do): every word 60% longer (a
translation's growth, a long player name), every number at 9,999,999, every digit-set number at its widest. The
preview's layout gates (overflow, squeeze, off screen) run on desktop and phone; only what the edge data BREAKS is
reported (the screen's own baseline warnings are not repeated).

    python kit/ui/fuzz.py <Screen> [--models src/ui] [--out build/ui] [--art build/ui/art]

-> build/ui/fuzz/<Screen>.json {cases: {long, max}: [{viewport, path, problem}]} + <Screen>.png (desktop, long case).
A digit-set number has a fixed row of cells: a value wider than its cells is reported (it cannot draw).
"""
import argparse
import copy
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import preview as P  # noqa: E402

TEXT = {"TextLabel", "TextButton", "TextBox"}
NUMERIC = re.compile(r"^[\s\d,.:%+\-xX/$R]*\d[\s\d,.:%+\-xX/$R]*$")


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def stretch(text):
    """a word 60% longer (keeps its case: a title stays a title)"""
    if not text.strip():
        return text
    if NUMERIC.match(text):
        return "9,999,999"
    extra = text[: max(1, int(len(text) * 0.6))]
    return text + " " + extra.strip()


def edge(model, case):
    """the model with every text pushed to the case ("long" | "max"), and the digit-set numbers too narrow to draw it"""
    m = copy.deepcopy(model)
    narrow = []

    def walk(inst, path):
        p = inst.get("Properties") or {}
        a = (p.get("Attributes") or {}).get("Attributes") or {}
        name = str(inst.get("Name") or "")
        # (a 1-2 character text is a tracked glyph, a key letter or an icon character: it does not grow in translation)
        if inst.get("ClassName") in TEXT and isinstance(p.get("Text"), str) and not name.startswith("Fx_")                 and len(p["Text"].strip()) > 2:
            t = p["Text"]
            if case == "long":
                p["Text"] = stretch(t)
            elif case == "max" and NUMERIC.match(t or "x"):
                p["Text"] = "9,999,999"
        if (a.get("Kit_Digits") or {}).get("String") and case == "max":
            cells = [c for c in inst.get("Children") or [] if str(c.get("Name", "")).startswith("C")]
            shown = str((a.get("Kit_Number") or {}).get("String") or "")
            need = len(shown) + 2
            if sum(ch.isdigit() for ch in shown) >= 2 and need > len(cells):  # (a NUMBER: a rank letter does not widen)
                narrow.append((path, f"a digit-set number with {len(cells)} cells: a value 2 digits wider ({need}) cannot draw — "
                                     "give it more cells (its \"text\" sets the count) or a short format"))
        for c in inst.get("Children") or []:
            walk(c, f"{path}.{c.get('Name')}")

    for r in m.get("Children") or []:
        walk(r, r.get("Name"))
    return m, narrow


def problems(model, label, sw, sh):
    _, checks = P.draw_viewport(model, sw, sh, label)
    return {(label, path, kind): msg for kind, path, msg in checks if kind in ("text_overflow", "squeezed", "offscreen")}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("screen")
    ap.add_argument("--models", default="src/ui")
    ap.add_argument("--out", default="build/ui")
    ap.add_argument("--art", default=None)
    a = ap.parse_args(argv)
    mp = os.path.join(a.models, f"{a.screen}.model.json")
    if not os.path.isfile(mp):
        return emit("fail", f"fuzz: no compiled {mp}", "lune run kit ui")
    with open(mp, encoding="utf-8") as fh:
        model = json.load(fh)
    P.ART_DIR = a.art or os.path.join(a.out, "art")
    views = [("desktop", 1920, 1080), ("phone", 844, 390)]
    base = {}
    for label, sw, sh in views:
        base.update(problems(model, label, sw, sh))
    report = {}
    for case in ("long", "max"):
        m, narrow = edge(model, case)
        found = []
        for label, sw, sh in views:
            for (vp, path, kind), msg in problems(m, label, sw, sh).items():
                if (vp, path, kind) not in base:
                    found.append({"viewport": vp, "path": path, "problem": kind, "fix": msg})
        found += [{"viewport": "any", "path": pth, "problem": "digits", "fix": msg} for pth, msg in narrow]
        report[case] = found
        if case == "long":
            im, _ = P.draw_viewport(m, 1920, 1080, "desktop")
            os.makedirs(os.path.join(a.out, "fuzz"), exist_ok=True)
            im.convert("RGB").save(os.path.join(a.out, "fuzz", f"{a.screen}.png"))
    out = os.path.join(a.out, "fuzz", f"{a.screen}.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"schema": 1, "screen": a.screen, "cases": report}, fh, indent=1)
    n = sum(len(v) for v in report.values())
    if n == 0:
        return emit("pass", f"fuzz: {a.screen} holds under long words and 9,999,999 (desktop + phone)", "none - proceed", report=out.replace(chr(92), "/"))
    first = next(f for v in report.values() for f in v)
    return emit("pass", f"fuzz: {a.screen} - {n} break(s) under edge data ({', '.join(f'{k}: {len(v)}' for k, v in report.items())})",
                f"improve {a.screen} [{first['viewport']}] {first['path']}: {first['fix']}", report=out.replace(chr(92), "/"))


if __name__ == "__main__":
    sys.exit(main())
