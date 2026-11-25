"""partsheet.py — compose the per-part review sheets (system python + PIL).

    python kit/blender/partsheet.py build/renders/parts/<asset>/index.json [--todo-only]

Reads the tiles rbx_inspect.part_tiles rendered (each part family: in context, orange on pale, and isolated) and
writes build/renders/parts/<asset>_parts_<k>.png — 12 families per sheet, captioned with the family name, how much
of it can be seen, its size and materials. These are what assets/models/<asset>.parts.md is answered from.
The families the review is asking about (new, changed, or marked fix) also get their own sheet(s):
<asset>_parts_todo.png — look there first. --todo-only (a --geo check) writes just those.
"""

import json
import os
import sys

from PIL import Image, ImageDraw

from labels import font, save

COLS, ROWS, TILE = 3, 4, 300
CAP = 46


def _sheet(chunk, root, path, f_big, f_small):
    cw, ch = TILE * 2 + 8, TILE + CAP
    sheet = Image.new("RGB", (COLS * cw + 8, ROWS * ch + 8), (34, 35, 38))
    d = ImageDraw.Draw(sheet)
    for i, f in enumerate(chunk):
        x, y = 4 + (i % COLS) * cw, 4 + (i // COLS) * ch
        for j, tile in enumerate(f["tiles"]):
            p = os.path.join(root, tile)
            if os.path.isfile(p):
                im = Image.open(p).convert("RGB").resize((TILE, TILE))
                sheet.paste(im, (x + j * (TILE + 4), y + CAP))
        n = len(f["members"])
        d.text((x + 4, y + 3), f"{f['family']}" + (f"  x{n}" if n > 1 else ""), fill=(255, 170, 60), font=f_big)
        d.text((x + 4, y + 25), f"seen {f['visible']:.0%} ({', '.join(f['seen_from'][:2]) or 'hidden'}) · "
               f"{f['size']} · {', '.join(f['materials'][:3])}", fill=(205, 205, 210), font=f_small)
    save(sheet, path)
    return os.path.relpath(path).replace("\\", "/")


def main(index_path, todo_only=False):
    with open(index_path, encoding="utf-8") as fh:
        idx = json.load(fh)
    root = os.path.dirname(index_path)
    fams = idx["families"]
    asset = idx["asset"]
    todo = set(idx.get("todo", []))
    out_dir = os.path.dirname(root)
    per = COLS * ROWS
    f_big, f_small = font(17), font(13)
    for old in os.listdir(out_dir):
        stale = old.startswith(f"{asset}_parts_todo") or (not todo_only and old.startswith(f"{asset}_parts_"))
        if stale and old.endswith(".png"):
            os.remove(os.path.join(out_dir, old))
    sheets, todo_sheets = [], []
    if not todo_only:
        for k in range(0, len(fams), per):
            path = os.path.join(out_dir, f"{asset}_parts_{k // per + 1}.png")
            sheets.append(_sheet(fams[k:k + per], root, path, f_big, f_small))
    asked = [f for f in fams if f["family"] in todo]
    for k in range(0, len(asked), per):
        path = os.path.join(out_dir, f"{asset}_parts_todo" + (f"_{k // per + 1}" if k else "") + ".png")
        todo_sheets.append(_sheet(asked[k:k + per], root, path, f_big, f_small))
    first = (todo_sheets or sheets or ["-"])[0]
    print(json.dumps({"schema": 1, "status": "pass",
                      "summary": f"part sheets {asset}: {len(fams)} families"
                                 + (f" on {len(sheets)} sheet(s)" if sheets else "")
                                 + f"; {len(asked)} to answer" + (f" on {first}" if todo_sheets else ""),
                      "next_action": (f"look at {first} and answer those lines in assets/models/{asset}.parts.md"
                                      if todo_sheets else f"nothing to answer — every part of {asset} is reviewed"),
                      "sheets": sheets, "todo_sheets": todo_sheets}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], "--todo-only" in sys.argv[2:]))
