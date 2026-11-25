"""words.py — the lettering step of `kit ui`: every label / button whose spec says `"lettering"` is baked into
display lettering art BEFORE the plates step copies the identity's art, so a screen author writes text and gets
Persona-type (or flat) lettering with no hand-run command.

    python kit/ui/words.py [--ui assets/ui] [--art assets/ui/art]

A node opts in with `"lettering": true` (the identity's `"lettering"` defaults) or a table of overrides:
    {"type": "button", "text": "NEW GAME", "lettering": {"size": 110, "seed": 23}}
Keys (kit/ui/letter.py flags, snake_case): style (persona | flat), size, font, outline, rim_px, rim_color, shadow,
shadow_color, wobble, overlap, seed, lean, caps, cards, card_color, fill, ink, accent, accent_share, track, name.
The piece is art:<identity>/w_<slug of the text> (or `name`); its .letter.json keeps the recipe, and a word is
re-baked only when its recipe changes. Two different recipes for one name are an error (give one a `name`).
The compiler (kit/lib/ui.luau) swaps the text for the piece and keeps the text as the Kit_Text attribute.
"""
import argparse
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import letter as L  # noqa: E402

KEYS = ["style", "size", "font", "outline", "rim_px", "rim_color", "shadow", "shadow_color", "wobble", "overlap", "seed",
        "lean", "shear", "caps", "cards", "card_color", "fill", "ink", "accent", "accent_share", "track", "weight",
        "bounce", "drip", "drip_share", "drip_phase", "arc", "inline", "inline_px", "inline_gap", "glow", "glow_px",
        "glow_alpha"]
FLAGS_BOOL = {"caps", "cards"}


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def slug(text):
    """the piece name for a text — the compiler computes the same (kit/lib/ui.luau letteringName)"""
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return "w_" + (s[:40] or "word")


def walk(node, out, path):
    if not isinstance(node, dict):
        return
    if node.get("lettering") not in (None, False) and isinstance(node.get("text"), str) and node["text"].strip():
        out.append((path + "." + str(node.get("name", "?")), node))
    for c in node.get("children") or []:
        walk(c, out, path + "." + str(node.get("name", "?")))


def recipe(node, defaults, tokens):
    r = dict(defaults)
    if isinstance(node.get("lettering"), dict):
        r.update(node["lettering"])
    r.setdefault("style", "persona")
    r.setdefault("size", node.get("textSize") or 96)
    r.setdefault("seed", sum(ord(c) for c in node["text"]) % 97 + 1)
    # colour tokens ("accent", "paper") resolve through the identity
    for k in ("fill", "ink", "accent", "shadow_color", "rim_color", "card_color", "inline", "glow"):
        v = r.get(k)
        if isinstance(v, str) and not v.startswith("#") and v in tokens:
            r[k] = tokens[v]
    return {k: r[k] for k in KEYS if k in r and r[k] is not None}


def argv_for(target, text, rec, art):
    argv = [target, "--text", text, "--art", art]
    for k, v in rec.items():
        flag = "--" + k.replace("_", "-")
        if k in FLAGS_BOOL:
            if v:
                argv.append(flag)
        else:
            argv += [flag, str(v)]
    return argv


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ui", default="assets/ui")
    ap.add_argument("--art", default="assets/ui/art")
    a = ap.parse_args()
    wanted = {}  # (identity, name) -> (text, recipe, where)
    errors = []
    for spec_path in sorted(glob.glob(os.path.join(a.ui, "*.json"))):
        base = os.path.basename(spec_path)[:-5]
        if "." in base:
            continue
        try:
            spec = json.load(open(spec_path, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        found = []
        walk(spec.get("root"), found, spec.get("name", base))
        if not found:
            continue
        ident = spec.get("identity")
        if not ident:
            errors.append(f"{base}: lettering needs the screen's \"identity\"")
            continue
        id_path = os.path.join(a.ui, "identities", ident + ".json")
        idj = json.load(open(id_path, encoding="utf-8")) if os.path.isfile(id_path) else {}
        defaults = idj.get("lettering") or {}
        tokens = idj.get("tokens") or {}
        for where, node in found:
            rec = recipe(node, defaults, tokens)
            name = (node["lettering"].get("name") if isinstance(node["lettering"], dict) else None) or slug(node["text"])
            key = (ident, name)
            if key in wanted and (wanted[key][0] != node["text"] or wanted[key][1] != rec):
                errors.append(f"{where}: '{name}' is already lettered differently at {wanted[key][2]} — give one a \"lettering\": {{\"name\": ...}}")
                continue
            wanted[key] = (node["text"], rec, where)
    baked, kept = [], 0
    for (ident, name), (text, rec, where) in sorted(wanted.items()):
        side_path = os.path.join(a.art, ident, name + ".letter.json")
        png = os.path.join(a.art, ident, name + ".png")
        if os.path.isfile(side_path) and os.path.isfile(png):
            try:
                side = json.load(open(side_path, encoding="utf-8"))
            except Exception:  # noqa: BLE001
                side = {}
            if side.get("recipe") == rec and side.get("text") == text:
                kept += 1
                continue
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = L.main(argv_for(f"{ident}/{name}", text, rec, a.art))
        if code != 0:
            errors.append(f"{where}: lettering '{text}' failed: {buf.getvalue().strip()[:200]}")
            continue
        side = json.load(open(side_path, encoding="utf-8"))
        side["recipe"] = rec
        side["used_by"] = where
        with open(side_path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(side, fh, indent=1)
        baked.append(f"{ident}/{name}")
    if errors:
        return emit("fail", f"words: {len(errors)} problem(s); {len(baked)} baked, {kept} unchanged", errors[0], errors=errors)
    return emit("pass", f"words: {len(wanted)} lettered word(s) — {len(baked)} baked" + (f" ({', '.join(baked[:6])}{'…' if len(baked) > 6 else ''})" if baked else "") + f", {kept} unchanged",
                "none — proceed" if not baked else "LOOK at the new words on their screens (kit ui --motion)", baked=baked)


if __name__ == "__main__":
    raise SystemExit(main())
