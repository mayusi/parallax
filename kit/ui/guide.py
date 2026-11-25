"""guide.py — an identity's STYLE GUIDE as one page (v7.16): what a studio hands every artist and engineer so a new
screen comes out in the same game — the colour tokens (swatches, their contrast on the ground), the type roles drawn
in their real faces, radius / minimums, the shape language, motion, lettering, the bans, the references it was
measured from, its drawn pieces and every screen that wears it (the preview frames).

    python kit/ui/guide.py <identity> [--ui assets/ui] [--build build/ui] [--out build/ui/guide]

-> build/ui/guide/<identity>.html (self-contained: pictures inlined as small thumbnails; reference stills are LINKED,
never copied in). Local only: nothing leaves the machine.
"""
import argparse
import base64
import html
import io
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}, ensure_ascii=False))
    return 0 if status == "pass" else 1


def hex_rgb(h):
    h = str(h).lstrip("#")
    if len(h) != 6:
        return None
    try:
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


def luminance(rgb):
    def ch(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def thumb(path, w=320):
    try:
        im = Image.open(path).convert("RGB")
    except Exception:  # noqa: BLE001
        return None
    if im.width > w:
        im = im.resize((w, max(1, round(im.height * w / im.width))), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=82)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def png_uri(im):
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def font_sample(face, size, text, color, bg):
    """the role drawn in its REAL face (the preview's font finder), or None when the face is not on this machine"""
    try:
        import preview as P
        f = P.font(face, min(int(size), 72))
        if face in P.FALLBACK_FACES or not isinstance(f, ImageFont.FreeTypeFont):
            return None
    except Exception:  # noqa: BLE001
        return None
    w = min(900, int(f.getlength(text)) + 24)
    h = int(min(size, 72) * 1.5) + 8
    im = Image.new("RGB", (max(w, 40), h), bg)
    ImageDraw.Draw(im).text((12, 4), text, font=f, fill=color)
    return png_uri(im)


def screens_of(identity, ui_dir):
    out = []
    for f in sorted(os.listdir(ui_dir)):
        if not f.endswith(".json"):
            continue
        try:
            with open(os.path.join(ui_dir, f), encoding="utf-8") as fh:
                d = json.load(fh)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(d, dict) and d.get("identity") == identity:
            out.append((f[:-5], d))
    return out


def build(identity, ui_dir="assets/ui", build_dir="build/ui"):
    """-> (html text, stats) for one identity"""
    with open(os.path.join(ui_dir, "identities", f"{identity}.json"), encoding="utf-8") as fh:
        ident = json.load(fh)
    tokens = ident.get("tokens") or {}
    fonts = ident.get("fonts") or {}
    ground = hex_rgb(tokens.get("bg")) or (20, 20, 24)
    panel = hex_rgb(tokens.get("panel")) or ground
    text_rgb = hex_rgb(tokens.get("text")) or (240, 240, 240)
    e = html.escape
    parts = []

    sw = []
    for k, v in tokens.items():
        rgb = hex_rgb(v)
        if not rgb:
            continue
        cg, cp = contrast(rgb, ground), contrast(rgb, panel)
        fg = "#000" if luminance(rgb) > 0.4 else "#fff"
        sw.append(f'<div class="sw"><div class="chip" style="background:{e(v)};color:{fg}">{e(k)}</div>'
                  f'<code>{e(v)}</code><small>on bg {cg:.1f}:1 · on panel {cp:.1f}:1</small></div>')
    parts.append(f"<h2>Colour tokens</h2><p class=note>Contrast against the ground and the panel; text needs 4.5:1, "
                 f"big text and icons 3:1.</p><div class=grid>{''.join(sw)}</div>")

    rows = []
    for role, r in (ident.get("roles") or {}).items():
        face = fonts.get(r.get("font") or "font") or r.get("font") or "?"
        col = hex_rgb(tokens.get(r.get("color") or "text")) or text_rgb
        size = r.get("size") or 20
        word = "SMASH 1,250" if role in ("number", "rank", "title") else "The quick brown fox — 1,250 coins"
        uri = font_sample(face, size, word, col, panel)
        pic = f'<img src="{uri}">' if uri else f'<span class="miss">({e(face)} not on this machine: kit ui fonts)</span>'
        rows.append(f"<tr><td><b>{e(role)}</b></td><td>{e(face)}</td><td>{e(str(size))} px</td><td>{pic}</td></tr>")
    parts.append(f"<h2>Type roles</h2><table>{''.join(rows)}</table>")

    def kv(title, d):
        if not d:
            return ""
        items = "".join(f"<tr><td><b>{e(str(k))}</b></td><td><code>{e(json.dumps(v, ensure_ascii=False))}</code></td></tr>" for k, v in d.items())
        return f"<h2>{e(title)}</h2><table>{items}</table>"

    for key, title in (("radius", "Radius"), ("minimums", "Minimums (px at 1080p)"), ("shape", "Shape language"),
                       ("motion", "Motion"), ("lettering", "Lettering"), ("bursts", "Bursts")):
        parts.append(kv(title, ident.get(key) if isinstance(ident.get(key), dict) else {}))

    bans = ident.get("bans") or []
    if bans:
        parts.append("<h2>Bans</h2><ul>" + "".join(f"<li>{e(str(b))}</li>" for b in bans) + "</ul>")

    refs = ident.get("references") or []
    if refs:
        li = []
        for r in refs:
            img = r.get("image") or ""
            link = f'<a href="../../../{e(img)}">{e(img)}</a>' if img else ""
            li.append(f"<li><b>{e(str(r.get('game') or ''))}</b> — {e(str(r.get('screen') or ''))} {link}<br><small>{e(str(r.get('take') or ''))}</small></li>")
        parts.append("<h2>Measured from</h2><ul class=refs>" + "".join(li) + "</ul>")

    art_dir = os.path.join(ui_dir, "art", identity)
    pieces = []
    if os.path.isdir(art_dir):
        files = sorted(os.listdir(art_dir))
        glyph_sets = {f[: -len(".glyphs.json")] for f in files if f.endswith(".glyphs.json")}
        for f in files:
            if f.split("_", 1)[0] in glyph_sets and "_" in f:
                continue  # (a bitmap font's letter cells: the type roles show the face)
            if f.endswith(".png") and len(pieces) < 48:
                uri = thumb(os.path.join(art_dir, f), 140)
                if uri:
                    pieces.append(f'<figure class=piece><img src="{uri}"><figcaption>{e(f[:-4])}</figcaption></figure>')
    if pieces:
        parts.append(f"<h2>Drawn pieces</h2><div class=pieces>{''.join(pieces)}</div>")

    screens = screens_of(identity, ui_dir)
    figs = []
    for name, spec in screens:
        p = os.path.join(build_dir, f"{name}.desktop.png")
        if not os.path.isfile(p):
            p = os.path.join(build_dir, f"{name}.png")
        uri = thumb(p, 480) if os.path.isfile(p) else None
        cap = f"{e(name)} — {e(str(spec.get('kind') or ''))}" + (f" · focus <code>{e(str(spec['focus']))}</code>" if spec.get("focus") else "")
        figs.append(f'<figure>{f"<img src={chr(34)}{uri}{chr(34)}>" if uri else "<p class=miss>(no preview: kit ui)</p>"}<figcaption>{cap}</figcaption></figure>')
    if figs:
        parts.append(f"<h2>Screens wearing it ({len(figs)})</h2><div class=screens>{''.join(figs)}</div>")

    accent = tokens.get("accent") or "#ffffff"
    doc = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(identity)} style guide</title><style>
body{{background:#121216;color:#e8e8ee;font:15px/1.45 system-ui,sans-serif;margin:0;padding:24px 16px;max-width:1200px;margin:auto}}
h1{{margin:0 0 4px;border-left:8px solid {e(accent)};padding-left:12px}} h2{{margin:28px 0 8px;color:#fff}}
.about{{color:#b8b8c8;max-width:900px}} .note{{color:#99a;margin:0 0 8px}} code{{color:#cde}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:10px}}
.sw{{background:#1c1c22;border-radius:6px;padding:8px}} .chip{{height:52px;border-radius:4px;display:flex;align-items:end;padding:4px 6px;font-weight:600;border:1px solid #333}}
.sw small{{display:block;color:#99a}} table{{border-collapse:collapse;width:100%}} td{{border-bottom:1px solid #2a2a33;padding:6px;vertical-align:top}}
.pieces{{display:flex;flex-wrap:wrap;gap:8px}} .piece{{margin:0;width:140px}} .piece img{{max-width:140px;background:repeating-conic-gradient(#2a2a30 0 25%,#1e1e24 0 50%) 0/16px 16px}}
.piece figcaption,.screens figcaption{{font-size:12px;color:#aab;word-break:break-all}} .screens{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}}
.screens figure{{margin:0}} .screens img,td img{{max-width:100%}} .miss{{color:#c88}} .refs li{{margin-bottom:8px}} a{{color:#9cf}}
</style></head><body><h1>{e(identity)} — style guide</h1><p class=about>{e(str(ident.get('about') or ''))}</p>
{''.join(parts)}<p class=note>Made by <code>lune run kit ui guide {e(identity)}</code> from assets/ui/identities/{e(identity)}.json.</p></body></html>"""
    return doc, {"tokens": len(sw), "roles": len(rows), "pieces": len(pieces), "screens": len(figs), "refs": len(refs)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("identity")
    ap.add_argument("--ui", default="assets/ui")
    ap.add_argument("--build", default="build/ui")
    ap.add_argument("--out", default="build/ui/guide")
    a = ap.parse_args(argv)
    if not os.path.isfile(os.path.join(a.ui, "identities", f"{a.identity}.json")):
        have = sorted(f[:-5] for f in os.listdir(os.path.join(a.ui, "identities")) if f.endswith(".json"))
        return emit("fail", f"guide: no identity {a.identity}", f"one of: {', '.join(have)}")
    doc, st = build(a.identity, a.ui, a.build)
    os.makedirs(a.out, exist_ok=True)
    out = os.path.join(a.out, f"{a.identity}.html")
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(doc)
    return emit("pass", f"guide {a.identity}: {st['tokens']} tokens, {st['roles']} type roles, {st['pieces']} pieces, "
                f"{st['screens']} screens -> {out}", f"open {out} in a browser (hand it to whoever builds the next screen)",
                page=out.replace(chr(92), "/"), **st)


if __name__ == "__main__":
    sys.exit(main())
