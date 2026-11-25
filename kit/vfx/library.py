"""library.py — the texture library sheet: every registered VFX texture (assets/effects/_textures.json) as a labelled
tile — first frame (or the whole strip for a 1-grid), recipe, grid, size, upload state and which presets / parts use
it — so a model picks an existing element before rendering a new one (reuse everything).

    python kit/vfx/library.py [--registry assets/effects/_textures.json] [--specs assets/textures]
                              [--effects assets/effects] [--out build/textures]

Writes build/textures/_library.png (tiles) and _library.md (the table). Prints one JSON line.
"""

import glob
import json
import os
import sys

from PIL import Image, ImageDraw


def load(path, default):
    if not os.path.isfile(path):
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def users(effects_dir):
    """texture key -> sorted preset / part names that reference it (any string value equal to the key)"""
    out = {}

    def walk(v, name):
        if isinstance(v, dict):
            for k, x in v.items():
                if k == "texture" and isinstance(x, str):
                    out.setdefault(x, set()).add(name)
                else:
                    walk(x, name)
        elif isinstance(v, list):
            for x in v:
                walk(x, name)

    for path in sorted(glob.glob(os.path.join(effects_dir, "*.json")) + glob.glob(os.path.join(effects_dir, "parts", "*.json"))):
        base = os.path.basename(path)
        if base.startswith("_"):
            continue
        name = ("parts/" if os.sep + "parts" + os.sep in path or "/parts/" in path else "") + base[:-5]
        walk(load(path, {}), name)
    return {k: sorted(v) for k, v in out.items()}


def main():
    argv = sys.argv[1:]
    opts = {"--registry": "assets/effects/_textures.json", "--specs": "assets/textures", "--effects": "assets/effects", "--out": "build/textures"}
    for i in range(0, len(argv) - 1, 2):
        opts[argv[i]] = argv[i + 1]
    reg = load(opts["--registry"], {})
    used = users(opts["--effects"])
    rows, tiles = [], []
    for key in sorted(k for k in reg if not k.startswith("_")):
        entry = reg[key] if isinstance(reg[key], dict) else {}
        spec = load(os.path.join(opts["--specs"], f"{key}.json"), {})
        grid = entry.get("grid", 1)
        file = entry.get("file") or ""
        if not os.path.isfile(file):  # legacy entries point elsewhere ("vfx/out/x.png"): the built sheet is the truth
            file = os.path.join(opts["--out"], f"{key}.png")
        size = None
        img = None
        if os.path.isfile(file):
            img = Image.open(file).convert("RGBA")
            size = img.size
        rows.append({
            "texture": key,
            "pack": spec.get("pack") or ("own (" + str(spec.get("recipe")) + ")" if spec.get("recipe") not in (None, "import") else "import"),
            "recipe": spec.get("recipe") or spec.get("engine") or "-",
            "grid": grid,
            "size": f"{size[0]}x{size[1]}" if size else "missing",
            "uploaded": bool(entry.get("id")),
            "used_by": used.get(key, []),
        })
        if img is not None:
            cols = grid if isinstance(grid, int) else (grid[0] if isinstance(grid, list) else 1)
            rws = grid if isinstance(grid, int) else (grid[1] if isinstance(grid, list) else 1)
            cw, ch = img.width // max(1, cols), img.height // max(1, rws)
            # the frame nearest a third through the sheet (the element at its fullest)
            fi = min(cols * rws - 1, (cols * rws) // 3)
            cell = img.crop(((fi % cols) * cw, (fi // cols) * ch, (fi % cols + 1) * cw, (fi // cols + 1) * ch)) if cols * rws > 1 else img
            cell.thumbnail((192, 192))
            tile = Image.new("RGB", (200, 232), (28, 28, 32))
            base = Image.new("RGBA", cell.size, (0, 0, 0, 255))
            tile.paste(Image.alpha_composite(base, cell).convert("RGB"), (4 + (192 - cell.width) // 2, 4 + (192 - cell.height) // 2))
            d = ImageDraw.Draw(tile)
            d.text((6, 200), key[:26], fill=(235, 235, 235))
            d.text((6, 214), f"{rows[-1]['recipe']} {cols}x{rws} {'up' if entry.get('id') else 'local'} · {len(used.get(key, []))} use", fill=(150, 150, 160))
            tiles.append(tile)
    os.makedirs(opts["--out"], exist_ok=True)
    if tiles:
        per = 6
        W, H = 200 * min(per, len(tiles)), 232 * ((len(tiles) + per - 1) // per)
        sheet = Image.new("RGB", (W, H), (20, 20, 24))
        for i, t in enumerate(tiles):
            sheet.paste(t, ((i % per) * 200, (i // per) * 232))
        sheet.save(os.path.join(opts["--out"], "_library.png"))
    with open(os.path.join(opts["--out"], "_library.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("| texture | pack | recipe | grid | size | uploaded | used by |\n|---|---|---|---|---|---|---|\n")
        for r in sorted(rows, key=lambda r: (r["pack"], r["texture"])):
            fh.write(f"| {r['texture']} | {r['pack']} | {r['recipe']} | {r['grid']} | {r['size']} | {'yes' if r['uploaded'] else 'no'} | {', '.join(r['used_by']) or '-'} |\n")
        packs = {}
        for r in rows:
            packs[r["pack"]] = packs.get(r["pack"], 0) + 1
        fh.write("\n## Packs\n\n" + "\n".join(f"- {k}: {v} texture(s)" for k, v in sorted(packs.items())) + "\n")
    unused = [r["texture"] for r in rows if not r["used_by"]]
    print(json.dumps({
        "schema": 1,
        "status": "pass",
        "summary": f"{len(rows)} texture(s) in the library ({len(tiles)} built, {sum(1 for r in rows if r['uploaded'])} uploaded, {len(unused)} unused)",
        "next_action": f"LOOK at {opts['--out']}/_library.png before rendering a new element; unused: {', '.join(unused) or 'none'}",
        "rows": rows,
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
