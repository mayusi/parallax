"""look.py — kit look: judge a built asset's DETAIL where it shows (the owner judges close-ups: "the lines on the
blades", "the cannisters need touch ups" — a whole-asset sheet shows those as a few pixels).

    lune run kit look closeup <asset> --part <name[,name...]> [--view three-quarter|three-quarter-left|front|back|side|left|top|below]
    lune run kit look closeup <asset> --box cx,cy,cz,size   (the saved .blend's own frame: Blender world, studs)
    lune run kit look lookdev <asset>   (the whole asset under studio / courtyard / sunset / interior light + a clay
                                         pass, with the albedo check: build/renders/<asset>_lookdev.png)

--part: every part whose name contains one of the words (BladeL; Canister = both canisters), framed together from the
build's manifest (part_bounds: every part's box, written before the join). Writes build/renders/<asset>_closeup_<tag>
.png. Prints one JSON line (summary / next_action).
"""

import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
_KIT = os.path.join(REPO, "kit")
if _KIT not in sys.path:
    sys.path.insert(0, _KIT)
from blender_path import find_blender  # noqa: E402

EXPORTS = os.path.join(REPO, os.environ.get("KIT_BUILD", "build"), "models")
RENDERS = os.path.join(REPO, os.environ.get("KIT_BUILD", "build"), "renders")


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def blender():
    return find_blender()


def frame(bounds, words):
    """the parts whose names contain any of `words` -> (centre (3,), size, matched names); None when none match"""
    hits = [n for n in bounds if any(w.lower() in n.lower() for w in words)]
    if not hits:
        return None
    lo = [min(bounds[n][0][i] for n in hits) for i in range(3)]
    hi = [max(bounds[n][1][i] for n in hits) for i in range(3)]
    centre = [(a + b) / 2 for a, b in zip(lo, hi)]
    size = max(max(b - a for a, b in zip(lo, hi)), 1e-4)
    return centre, size, hits


def arg(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


def albedo_check(color_png, metal_png):
    """the baked colour's non-metal texels against the 30-240 sRGB rule (darker than charcoal or brighter than fresh
    snow reads wrong under a sun) -> (share too dark, share too bright, p5, p95)"""
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    c = np.asarray(Image.open(color_png).convert("RGB"), np.float32)
    m = np.asarray(Image.open(metal_png).convert("L"), np.float32) if os.path.isfile(metal_png) else np.zeros(c.shape[:2])
    lum = c.mean(axis=2)
    keep = (m < 128) & (lum > 3)   # (the atlas' empty background is black: not a surface)
    if not keep.any():
        return 0.0, 0.0, 0.0, 0.0
    v = lum[keep]
    return float((v < 30).mean()), float((v > 240).mean()), float(np.percentile(v, 5)), float(np.percentile(v, 95))


def lookdev(asset, blend):
    """the lookdev sheet: 4 lights + clay, labelled, the albedo check under it"""
    from PIL import Image, ImageDraw  # noqa: PLC0415

    tmp = os.path.join(RENDERS, f"{asset}_lookdev")
    p = subprocess.run([blender(), "-b", blend, "-P", os.path.join(REPO, "kit", "blender", "look_lookdev.py"), "--",
                        tmp], capture_output=True, text=True, timeout=1800)
    names = ["studio", "courtyard", "sunset", "interior", "clay"]
    if "LOOKDEV_RENDERED" not in p.stdout:
        return emit("fail", f"look lookdev: the render failed: {(p.stderr or p.stdout)[-240:]}", "read the error above")
    tiles = [Image.open(os.path.join(tmp, f"{n}.png")).convert("RGB") for n in names]
    tw, th = tiles[0].size
    sheet = Image.new("RGB", (tw * 3, th * 2 + 40), (24, 24, 26))
    dr = ImageDraw.Draw(sheet)
    for i, (n, t) in enumerate(zip(names, tiles)):
        x, y = (i % 3) * tw, (i // 3) * th
        sheet.paste(t, (x, y))
        dr.rectangle([x, y, x + 120, y + 22], fill=(0, 0, 0))
        dr.text((x + 6, y + 5), n.upper(), fill=(255, 220, 120))
    tex = os.path.join(EXPORTS, "textures")
    dark, bright, p5, p95 = albedo_check(os.path.join(tex, f"{asset}_color.png"), os.path.join(tex, f"{asset}_metal.png"))
    ok = dark < 0.02 and bright < 0.02
    line = (f"albedo (non-metal, sRGB): p5 {p5:.0f} / p95 {p95:.0f}; {dark:.1%} under 30, {bright:.1%} over 240 — "
            + ("PASS" if ok else "CHECK: outside the 30-240 rule"))
    dr.text((10, th * 2 + 12), line, fill=(120, 230, 140) if ok else (255, 140, 120))
    out = os.path.join(RENDERS, f"{asset}_lookdev.png")
    sheet.save(out)
    rel = os.path.relpath(out, REPO).replace(os.sep, "/")
    return emit("pass", f"look lookdev {asset}: 4 lights + clay -> {rel}; {line}",
                f"LOOK at {rel}: does every material hold under every light? the clay: is the FORM right alone?",
                image=rel, albedo={"under_30": round(dark, 4), "over_240": round(bright, 4), "p5": p5, "p95": p95})


SHEET_TILES = [("owner", "YOUR VIEW (forest)"), ("roblox_day", "ROBLOX LOOK - DAY"), ("roblox_night", "ROBLOX LOOK - AS READ"),
               ("clay", "CLAY (form alone)"), ("wire", "WIREFRAME"), ("texels", "TEXEL CHECKER")]


def sheet(asset, blend, game):
    """the presentation sheet (3D crafts plan S0): six looks from one hero camera (kit/blender/look_sheet.py) and every
    texture set's four maps, flat -> build/renders/<asset>_sheet.png"""
    from PIL import Image, ImageDraw  # noqa: PLC0415

    tmp = os.path.join(RENDERS, f"{asset}_sheet")
    cmd = [blender(), "-b", blend, "-P", os.path.join(REPO, "kit", "blender", "look_sheet.py"), "--", tmp]
    if game:
        cmd += ["--game", game]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    line = next((ln for ln in p.stdout.splitlines() if ln.startswith("LOOK_SHEET ")), None)
    if not line:
        return emit("fail", f"look sheet: the render failed: {(p.stderr or p.stdout)[-240:]}", "read the error above")
    info = json.loads(line[len("LOOK_SHEET "):])
    tiles = [Image.open(os.path.join(tmp, f"{t}.png")).convert("RGB") for t, _ in SHEET_TILES]
    tw, th = tiles[0].size
    try:
        with open(os.path.join(EXPORTS, f"{asset}.manifest.json"), encoding="utf-8") as fh:
            groups = json.load(fh).get("groups") or {}
    except (OSError, ValueError):
        groups = {}
    thumb, maps = 170, ("color", "rough", "metal", "normal")
    per_row = max(1, (tw * 3) // (thumb * len(maps)))   # texture sets side by side, as many as fit the width
    rows = (len(groups) + per_row - 1) // per_row
    band = thumb + 26
    sheet_img = Image.new("RGB", (tw * 3, th * 2 + rows * band + 34), (24, 24, 26))
    dr = ImageDraw.Draw(sheet_img)
    for i, ((key, title), t) in enumerate(zip(SHEET_TILES, tiles)):
        x, y = (i % 3) * tw, (i // 3) * th
        sheet_img.paste(t, (x, y))
        dr.rectangle([x, y, x + 8 + 7 * len(title), y + 20], fill=(0, 0, 0))
        dr.text((x + 5, y + 4), title, fill=(255, 220, 120))
    for gi, (g, gv) in enumerate(groups.items()):
        x0 = (gi % per_row) * thumb * len(maps)
        y0 = th * 2 + (gi // per_row) * band
        dr.text((x0 + 4, y0 + 6), f"texture set '{g}' ({gv.get('tris', '?')} tris): " + " / ".join(maps),
                fill=(200, 210, 230))
        for mi, mname in enumerate(maps):
            rel = (gv.get("textures") or {}).get(mname)
            pth = os.path.join(REPO, rel) if rel else None
            if pth and os.path.isfile(pth):
                im = Image.open(pth).convert("RGB").resize((thumb, thumb))
                sheet_img.paste(im, (x0 + mi * thumb, y0 + 22))
    note = f"Roblox look preset: {info.get('preset')} - {info['tiles'].get('roblox_day', '')[:120]}"
    dr.text((8, sheet_img.size[1] - 24), note, fill=(150, 160, 175))
    out = os.path.join(RENDERS, f"{asset}_sheet.png")
    sheet_img.save(out)
    rel = os.path.relpath(out, REPO).replace(os.sep, "/")
    # the RECORD of what was looked at: which build (its .blend and manifest, by size + modification time) made this
    # sheet — a later check can tell a sheet of THIS build from one of an older build (<asset>_sheet.json)
    import time  # noqa: PLC0415

    def stamp(path):
        try:
            st = os.stat(path)
            return {"path": os.path.relpath(path, REPO).replace(os.sep, "/"), "size": st.st_size,
                    "mtime_ns": st.st_mtime_ns}
        except OSError:
            return None
    record = {"asset": asset, "made": time.strftime("%Y-%m-%dT%H:%M:%S"), "sheet": rel, "game": game,
              "build": {"blend": stamp(blend), "manifest": stamp(os.path.join(EXPORTS, f"{asset}.manifest.json"))},
              "preset": info.get("preset"), "tiles": info["tiles"]}
    rec_path = os.path.join(RENDERS, f"{asset}_sheet.json")
    with open(rec_path, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=1)
    rec_rel = os.path.relpath(rec_path, REPO).replace(os.sep, "/")
    return emit("pass", f"look sheet {asset}: your view, the Roblox look (day, as read), clay, wireframe, texel checker "
                f"and {len(groups)} texture set(s) -> {rel}; {info['tiles'].get('wire', '')}",
                f"LOOK at {rel}: the form in clay, the triangles where the silhouette needs them, even texel squares, "
                "and the Roblox look beside your own view", image=rel, tiles=info["tiles"], record=rec_rel)


def zebra(asset, blend, argv):
    """the zebra test: every surface a glossy grey under striped light — dents, pinches and wavy faces break the
    stripes (kit/blender/look_ortho.py --zebra), one orthographic view of the parts named"""
    try:
        with open(os.path.join(EXPORTS, f"{asset}.manifest.json"), encoding="utf-8") as fh:
            bounds = json.load(fh).get("part_bounds") or {}
    except (OSError, ValueError):
        bounds = {}
    words = [w for w in (arg(argv, "--part", "") or "").split(",") if w] or [""]
    hits = [n for n in bounds if any(w.lower() in n.lower() for w in words)]
    if not hits:
        return emit("fail", f"look zebra: no part of {asset} matches {words}", "parts: " + ", ".join(sorted(bounds)[:20]))
    lo = [min(bounds[n][0][i] for n in hits) for i in range(3)]
    hi = [max(bounds[n][1][i] for n in hits) for i in range(3)]
    view = arg(argv, "--view", "side")
    tag = re.sub(r"[^A-Za-z0-9_]+", "_", "_".join(w for w in words if w))[:40] or "all"
    out = os.path.join(RENDERS, f"{asset}_zebra_{tag}_{view}.png")
    os.makedirs(RENDERS, exist_ok=True)
    p = subprocess.run([blender(), "-b", blend, "-P", os.path.join(REPO, "kit", "blender", "look_ortho.py"), "--", out,
                        ",".join(map(str, lo)), ",".join(map(str, hi)), "--view", view, "--zebra", "--px", "1800"],
                       capture_output=True, text=True, timeout=1800)
    if "LOOK_ORTHO" not in p.stdout or not os.path.isfile(out):
        return emit("fail", f"look zebra: the render failed: {(p.stderr or p.stdout)[-240:]}", "read the error above")
    rel = os.path.relpath(out, REPO).replace(os.sep, "/")
    return emit("pass", f"look zebra {asset}: {len(hits)} part(s), {view} -> {rel}",
                f"LOOK at {rel}: stripes that break, kink or wobble = a dent, a pinch or a wavy face (weighted normals, "
                "a cleaner fit, a support loop); smooth bends = a clean surface", image=rel)


def game_build(argv):
    """the build folder of the game the command is for (--game <Name> > env KIT_GAME > games/.active, as
    kit/lib/config.luau routes every path), relative to the repo; None = the project root's (a KIT_BUILD set by the
    caller always wins). `kit look ... --game SampleRegion` once looked in the root's build and found nothing"""
    if os.environ.get("KIT_BUILD"):
        return None
    game = argv[argv.index("--game") + 1] if "--game" in argv and argv.index("--game") + 1 < len(argv) else None
    game = game or os.environ.get("KIT_GAME")
    act = os.path.join(REPO, "games", ".active")
    if not game and os.path.isfile(act):
        game = open(act, encoding="utf-8").read().strip()
    if game and game.lower() != "none" and os.path.isdir(os.path.join(REPO, "games", game)):
        return os.path.join("games", game, "build")
    return None


def main(argv):
    global EXPORTS, RENDERS
    gb = game_build(argv)
    if gb:   # (set before the sub-tools are imported: each reads KIT_BUILD for its own folders)
        os.environ["KIT_BUILD"] = gb
        EXPORTS, RENDERS = os.path.join(REPO, gb, "models"), os.path.join(REPO, gb, "renders")
    game_name = None
    if "--game" in argv:
        i = argv.index("--game")
        game_name = argv[i + 1] if i + 1 < len(argv) else None
        argv = argv[:i] + argv[i + 2:]
    game_name = game_name or os.environ.get("KIT_GAME") or (os.path.basename(os.path.dirname(gb)) if gb else None)
    if game_name and game_name.lower() == "none":
        game_name = None
    if argv and argv[0] == "sheet" and len(argv) >= 2:
        blend = os.path.join(EXPORTS, f"{argv[1]}.blend")
        if not os.path.isfile(blend):
            return emit("fail", f"look: no build of {argv[1]}", f"lune run kit asset {argv[1]}")
        return sheet(argv[1], blend, game_name)
    if argv and argv[0] == "details":
        import look_details  # noqa: PLC0415

        return look_details.main(argv[1:])
    if argv and argv[0] == "silhouette":
        import look_silhouette  # noqa: PLC0415

        return look_silhouette.main(argv[1:])
    if argv and argv[0] == "edges":
        import look_edges  # noqa: PLC0415

        return look_edges.main(argv[1:])
    if argv and argv[0] == "zebra" and len(argv) >= 2:
        blend = os.path.join(EXPORTS, f"{argv[1]}.blend")
        if not os.path.isfile(blend):
            return emit("fail", f"look: no build of {argv[1]}", f"lune run kit asset {argv[1]}")
        return zebra(argv[1], blend, argv)
    if argv and argv[0] == "lookdev" and len(argv) >= 2:
        blend = os.path.join(EXPORTS, f"{argv[1]}.blend")
        if not os.path.isfile(blend):
            return emit("fail", f"look: no build of {argv[1]}", f"lune run kit asset {argv[1]}")
        return lookdev(argv[1], blend)
    if not argv or argv[0] != "closeup" or len(argv) < 2:
        return emit("fail", "look: needs closeup <asset> --part <name> | --box cx,cy,cz,size",
                    "lune run kit look closeup <asset> --part <part name>")
    asset = argv[1]
    blend = os.path.join(EXPORTS, f"{asset}.blend")
    if not os.path.isfile(blend):
        return emit("fail", f"look: no build of {asset}", f"lune run kit asset {asset}")
    view = arg(argv, "--view", "three-quarter")
    if "--box" in argv:
        vals = [float(v) for v in arg(argv, "--box").split(",")]
        centre, size, hits, tag = vals[:3], vals[3], [], "box"
    else:
        words = [w for w in (arg(argv, "--part", "") or "").split(",") if w]
        try:
            with open(os.path.join(EXPORTS, f"{asset}.manifest.json"), encoding="utf-8") as fh:
                bounds = json.load(fh).get("part_bounds") or {}
        except (OSError, ValueError):
            bounds = {}
        if not bounds:
            return emit("fail", f"look: {asset}'s manifest has no part bounds (built before kit look existed)",
                        f"lune run kit asset {asset} (once), then again")
        got = frame(bounds, words) if words else None
        if got is None:
            return emit("fail", f"look: no part of {asset} matches {words}",
                        "parts: " + ", ".join(sorted(bounds)[:30]))
        centre, size, hits = got
        tag = re.sub(r"[^A-Za-z0-9_]+", "_", "_".join(words))[:40]
    out = os.path.join(RENDERS, f"{asset}_closeup_{tag}{'' if view == 'three-quarter' else '_' + view}.png")
    os.makedirs(RENDERS, exist_ok=True)
    exe = blender()
    p = subprocess.run([exe, "-b", blend, "-P", os.path.join(REPO, "kit", "blender", "look_closeup.py"), "--", out,
                        *[str(v) for v in centre], str(size), "--view", view], capture_output=True, text=True,
                       timeout=900)
    if "LOOK_RENDERED" not in p.stdout or not os.path.isfile(out):
        return emit("fail", f"look: the render failed: {(p.stderr or p.stdout)[-240:]}", "read the error above")
    rel = os.path.relpath(out, REPO).replace(os.sep, "/")
    return emit("pass", f"look closeup {asset}: {len(hits) or 'a box'}{' part(s)' if hits else ''} framed ({view}) -> {rel}",
                f"LOOK at {rel}: the detail at hero distance", parts=hits, image=rel)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
