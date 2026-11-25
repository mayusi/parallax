"""material_labels.py — names every sphere of the material sheet (system python + PIL; Blender has none):

    python kit/blender/material_labels.py [build/materials/sheet.json]   -> build/materials/sheet.png

Under each sphere: its name (what rbx.real("<name>") takes) and its metalness / roughness as a build gets them.
Prints one JSON line: {status, summary, next_action}.
"""

import json
import os
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import labels  # noqa: E402  (the kit's font + safe save)


def main(argv):
    meta = argv[0] if argv else os.path.join(REPO, "build", "materials", "sheet.json")
    with open(meta, encoding="utf-8") as fh:
        d = json.load(fh)
    img = Image.open(d["picture"]).convert("RGB")
    draw = ImageDraw.Draw(img)
    f_name, f_val = labels.font(19), labels.font(15)
    for s in d["spots"]:
        name = s["name"] if len(s["name"]) <= 20 else s["name"][:19] + "."
        for text, f, dy, fill in ((name, f_name, 0, (240, 240, 244)),
                                  (f"metal {s['metal']:g}  rough {s['rough']:g}", f_val, 22, (190, 192, 198))):
            w = draw.textlength(text, font=f)
            x, y = s["x"] - w / 2, s["y"] + dy
            draw.text((x + 1, y + 1), text, font=f, fill=(0, 0, 0))
            draw.text((x, y), text, font=f, fill=fill)
    out = os.path.join(os.path.dirname(d["picture"]), "sheet.png")
    labels.save(img, out)
    print(json.dumps({"schema": 1, "status": "pass", "summary": f"material sheet: {len(d['spots'])} materials, "
                      f"named -> {os.path.relpath(out, REPO)}", "next_action": "look at it; build with "
                      "a.material(\"<name>\", **rbx.real(\"<Name>\"))", "sheet": out}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
