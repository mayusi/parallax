"""look.py — what `kit world look` shows: ONE PAGE PER STATION at full size (kit/world/lookpages.py: the reference
still above our labelled shot, the same framing) and the contact sheet of every station beside the world's reference
stills (<worlds>/refs/<Name>/*.png|jpg) - the sheet is the index and what a verdict records, the pages are what is
looked at. The world twin of the 3D lane's "look at the render beside the references".

Usage: python kit/world/worldlook.py <render_dir> <name> [--refs DIR]   -> build/worlds/look/<name>.png + <render_dir>/pages/
"""

import json
import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lookpages  # noqa: E402

BG, FG = (20, 22, 27), (232, 230, 225)


def tile(img, w):
    h = int(img.height * w / img.width)
    return img.resize((w, h), Image.LANCZOS)


def station_cells(rdir):
    """the sheet's cells of ours, in the renderer's own order -> [(label, path)]; a folder rendered before stations
    were written (no stations.json) shows its eye_* and over shots, as the sheet always did"""
    shots = sorted(f for f in os.listdir(rdir) if f.endswith(".png") and not f.endswith(".raw.png"))  # (labelled ones only)
    sp = os.path.join(rdir, "stations.json")
    if os.path.isfile(sp):
        with open(sp, encoding="utf-8") as fh:
            stations = json.load(fh).get("stations", [])
        return [(f"{s.get('title') or s['name']} ({s['name']})", os.path.join(rdir, s["name"] + ".png"))
                for s in stations if s.get("name") and s["name"] + ".png" in shots]
    eyes = [f for f in shots if f.startswith("eye_")]
    over = [f for f in shots if f.startswith("over")]
    return ([(f"player's eyes from spawn {f[4:-4]}", os.path.join(rdir, f)) for f in eyes]
            + [("establishing shot", os.path.join(rdir, f)) for f in over])


def main(argv):
    rdir, name = argv[0], argv[1]
    refs = argv[argv.index("--refs") + 1] if "--refs" in argv else os.path.join("assets", "worlds", "refs", name)
    ours = station_cells(rdir)
    if not ours:
        print(json.dumps({"status": "fail", "summary": f"no renders in {rdir}", "next_action": "the Blender step failed: read its output"}))
        return 1
    _, never, _ = lookpages.load_pairing(refs)
    # (a pairing file that cannot be read: its "never" list cannot be read either, so no still goes on the sheet)
    ref_imgs = [] if never is None else [os.path.join(refs, f) for f in lookpages.list_stills(refs)
                                         if f.lower() not in never][:lookpages.FIRST_STILLS]
    W = 520
    cells = ours + [(f"reference: {os.path.basename(p)}", p) for p in ref_imgs]
    cols = 3
    imgs = [(label, tile(Image.open(p).convert("RGB"), W)) for label, p in cells]
    rows = (len(imgs) + cols - 1) // cols
    rh = max(i.height for _, i in imgs) + 26
    sheet = Image.new("RGB", (cols * (W + 10) + 10, rows * (rh + 10) + 40), BG)
    d = ImageDraw.Draw(sheet)
    d.text((10, 10), f"{name}: every station (the index) - Blender preview, not Studio's lighting; full size, each beside its reference: {os.path.basename(os.path.normpath(rdir))}/pages/", fill=FG)
    for k, (label, im) in enumerate(imgs):
        x = 10 + (k % cols) * (W + 10)
        y = 40 + (k // cols) * (rh + 10)
        sheet.paste(im, (x, y + 20))
        d.text((x, y + 4), label, fill=(94, 200, 255) if label.startswith("reference") else FG)
    out = os.path.join(os.path.dirname(os.path.normpath(rdir)), f"{name}.png")
    sheet.save(out)
    pages = lookpages.build(rdir, name, refs_dir=refs)
    summary = f"{len(ours)} station(s)" + (f" beside {len(ref_imgs)} reference(s)" if ref_imgs else " (no references: " + refs.replace(os.sep, "/") + "/)")
    if pages["status"] != "pass":
        print(json.dumps({"status": "fail", "summary": summary + "; the station pages failed: " + pages["summary"],
                          "next_action": pages["next_action"], "sheet": out.replace(os.sep, "/")}))
        return 1
    print(json.dumps({"status": "pass", "summary": summary + "; " + pages["summary"],
                      "next_action": pages["look"] + f"; the index sheet: {out.replace(os.sep, '/')}",
                      "sheet": out.replace(os.sep, "/"), "pages": pages["pages"], "folder": pages["folder"],
                      "look": pages["look"], "by_order": pages["by_order"], "no_reference": pages["no_reference"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
