"""loc.py — a screen ready for other languages? Roblox auto-translates TEXT (AutoLocalize), never PICTURES: a lettered
word ("SMASH!", a title baked into art) stays English for every player. And translated text runs longer.

    python kit/ui/loc.py <Screen> [--models src/ui] [--ui assets/ui] [--out build/ui]

1. PSEUDO-LOCALIZATION: every text as "[Ŝĥöþ ····]" — accented (do the glyphs exist in the face? do diacritics clip
   at the top?), 40% longer (German, French, Russian grow), bracketed (a cut-off end shows) — rendered on desktop +
   phone; only what it breaks is reported.
2. LETTERED WORDS: every picture made by the letter route (its sidecar .letter.json) is listed with its words: each
   needs a translated version (letter it again per language) or a typed fallback.
-> build/ui/loc/<Screen>.json + <Screen>.png (the pseudo-localized desktop frame).
"""
import argparse
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import preview as P  # noqa: E402

ACCENT = str.maketrans("AaCcEeIiNnOoSsUuYyZzHhGgKkLlRrTt", "ÅåÇçÉéÎîÑñÖöŜŝÛûÝýŽžĤĥĜĝĶķĹĺŔŕŢţ")


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}, ensure_ascii=False))
    return 0 if status == "pass" else 1


def pseudo(text):
    """accented, 40% longer, bracketed — a pseudo-translation"""
    if not text.strip() or text.strip().replace(",", "").replace(".", "").isdigit():
        return text  # (numbers are universal)
    pad = "·" * max(1, round(len(text) * 0.4))
    return f"[{text.translate(ACCENT)} {pad}]"


def localize(model):
    m = copy.deepcopy(model)

    def walk(inst):
        p = inst.get("Properties") or {}
        if inst.get("ClassName") in ("TextLabel", "TextButton", "TextBox") and isinstance(p.get("Text"), str) \
                and not str(inst.get("Name") or "").startswith("Fx_") and len(p["Text"].strip()) > 2:
            p["Text"] = pseudo(p["Text"])
        for c in inst.get("Children") or []:
            walk(c)

    for r in m.get("Children") or []:
        walk(r)
    return m


def lettered(model, ui_dir):
    """[(path, piece, words)] — pictures made by the letter route (they will not translate)"""
    out = []

    def walk(inst, path):
        a = ((inst.get("Properties") or {}).get("Attributes") or {}).get("Attributes") or {}
        art = (a.get("KitArt") or {}).get("String")
        if art and inst.get("ClassName") in ("ImageLabel", "ImageButton") and not str(inst.get("Name") or "").startswith("Fx_"):
            side = os.path.join(ui_dir, "art", f"{art}.letter.json")
            if os.path.isfile(side):
                with open(side, encoding="utf-8") as fh:
                    words = json.load(fh).get("text")
                out.append((path, art, words))
        for c in inst.get("Children") or []:
            walk(c, f"{path}.{c.get('Name')}")

    for r in model.get("Children") or []:
        walk(r, r.get("Name"))
    return out


def export(models_dir, ui_dir, out_csv):
    """every typed text of every compiled screen -> a Roblox LocalizationTable CSV (Key, Context, Example, Source, en);
    a lettered word (a picture) is listed too, its Context saying it needs a per-language picture"""
    import csv
    rows, seen = [], set()
    for f in sorted(os.listdir(models_dir)):
        if not f.endswith(".model.json"):
            continue
        with open(os.path.join(models_dir, f), encoding="utf-8") as fh:
            model = json.load(fh)
        screen = f[: -len(".model.json")]

        def walk(inst, path):
            p = inst.get("Properties") or {}
            name = str(inst.get("Name") or "")
            if inst.get("ClassName") in ("TextLabel", "TextButton") and isinstance(p.get("Text"), str) and not name.startswith("Fx_"):
                t = p["Text"].strip()
                if len(t) > 1 and not t.replace(",", "").replace(".", "").isdigit() and (screen, t) not in seen:
                    seen.add((screen, t))
                    rows.append({"Key": f"{screen}.{path}", "Context": f"{screen}: {path}", "Example": "", "Source": t, "en": t})
            for c in inst.get("Children") or []:
                walk(c, f"{path}.{c.get('Name')}")

        for r in model.get("Children") or []:
            walk(r, r.get("Name"))
        for path, art, words in lettered(model, ui_dir):
            if words:
                rows.append({"Key": f"{screen}.{path}", "Context": f"{screen}: {path} - a LETTERED picture ({art}): "
                             "translate, then letter a version per language", "Example": "", "Source": str(words), "en": str(words)})
    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    with open(out_csv, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["Key", "Context", "Example", "Source", "en"])
        w.writeheader()
        w.writerows(rows)
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("screen", nargs="?")
    ap.add_argument("--models", default="src/ui")
    ap.add_argument("--ui", default="assets/ui")
    ap.add_argument("--out", default="build/ui")
    ap.add_argument("--art", default=None)
    ap.add_argument("--export", default=None, help="write every screen's texts to this LocalizationTable CSV")
    a = ap.parse_args(argv)
    if a.export:
        rows = export(a.models, a.ui, a.export)
        n_pic = sum(1 for r in rows if "LETTERED" in r["Context"])
        return emit("pass", f"loc: {len(rows)} text(s) -> {a.export} ({n_pic} lettered picture(s) need a version per language)",
                    "import it into the experience's LocalizationTable (Creator Dashboard: Localization), translate, and letter the pictures")
    mp = os.path.join(a.models, f"{a.screen}.model.json")
    if not os.path.isfile(mp):
        return emit("fail", f"loc: no compiled {mp}", "lune run kit ui")
    with open(mp, encoding="utf-8") as fh:
        model = json.load(fh)
    P.ART_DIR = a.art or os.path.join(a.out, "art")
    views = [("desktop", 1920, 1080), ("phone", 844, 390)]
    kinds = ("text_overflow", "squeezed", "offscreen")
    base = set()
    for label, sw, sh in views:
        _, checks = P.draw_viewport(model, sw, sh, label)
        base |= {(label, pth, k) for k, pth, _ in checks if k in kinds}
    m = localize(model)
    breaks = []
    for label, sw, sh in views:
        im, checks = P.draw_viewport(m, sw, sh, label)
        if label == "desktop":
            os.makedirs(os.path.join(a.out, "loc"), exist_ok=True)
            im.convert("RGB").save(os.path.join(a.out, "loc", f"{a.screen}.png"))
        breaks += [{"viewport": label, "path": pth, "problem": k, "fix": msg} for k, pth, msg in checks
                   if k in kinds and (label, pth, k) not in base]
    words = [{"path": p_, "piece": art, "words": w} for p_, art, w in lettered(model, a.ui)]
    out = os.path.join(a.out, "loc", f"{a.screen}.json")
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"schema": 1, "screen": a.screen, "pseudo_breaks": breaks, "lettered_words": words}, fh, indent=1, ensure_ascii=False)
    summary = f"loc: {a.screen} - {len(breaks)} break(s) under pseudo-localization, {len(words)} lettered word(s) that will not translate"
    if breaks:
        nxt = f"improve {a.screen} [{breaks[0]['viewport']}] {breaks[0]['path']}: {breaks[0]['fix']}"
    elif words:
        nxt = f"each lettered word needs a translated version or a typed fallback: {', '.join(repr(w['words']) for w in words[:4])}"
    else:
        nxt = "none - proceed"
    return emit("pass", summary, nxt, report=out.replace(chr(92), "/"))


if __name__ == "__main__":
    sys.exit(main())
