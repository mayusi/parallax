"""look_sheet.py — `python kit/anim/look_sheet.py <frames dir> [--every 2]`: the frames Blender rendered for a look
(kit/anim/look.py, one PNG per view per frame + look.json) -> <Name>.look.gif (the views side by side, every frame,
at the clip's own rate) and <Name>.look.png (a sheet of every Nth frame with its time) beside the frames dir."""

import json
import math
import os
import sys

from PIL import Image, ImageDraw


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def main(argv):
    if not argv:
        return emit("fail", "look_sheet: needs <frames dir>", "lune run kit anim look <Name>")
    frames_dir = argv[0]
    every = int(argv[argv.index("--every") + 1]) if "--every" in argv else 2
    manifest = os.path.join(frames_dir, "look.json")
    if not os.path.isfile(manifest):
        return emit("fail", f"look_sheet: no {manifest}", "lune run kit anim look <Name>")
    with open(manifest, encoding="utf-8") as fh:
        info = json.load(fh)
    name, fps, views, frames = info["name"], float(info["fps"]), info["views"], info["frames"]
    tiles = []
    for k, f in enumerate(frames):
        ims = [Image.open(os.path.join(frames_dir, f"{v}_{f:04d}.png")).convert("RGB") for v in views]
        w, h = ims[0].size
        tile = Image.new("RGB", (w * len(ims), h), (235, 236, 240))
        for i, im in enumerate(ims):
            tile.paste(im, (i * w, 0))
        d = ImageDraw.Draw(tile)
        d.text((8, 6), f"{name} ({info.get('rig', '')})  t={(f - frames[0]) / fps:.2f}s  {k + 1}/{len(frames)}", fill=(30, 30, 34))
        tiles.append(tile)
    out_dir = os.path.dirname(os.path.abspath(frames_dir))
    gif_path = os.path.join(out_dir, f"{name}.look.gif")
    # each frame shown for the time to the next rendered frame (a look may render every Nth frame of a 60 fps clip)
    steps = [(frames[k + 1] - frames[k]) if k + 1 < len(frames) else (frames[k] - frames[k - 1] if k else 1) for k in range(len(frames))]
    small = [t.resize((t.width // 2, t.height // 2)) for t in tiles]
    # an impact freeze at every Hit (the clip's feel.hitstop, default 3 frames): the GIF holds the rendered frame
    # nearest the Hit (hits are FRAME NUMBERS, as the look renders them)
    hits, stop = info.get("hits") or [], int(info.get("hitstop_frames") or 0)
    held = {min(range(len(frames)), key=lambda k: abs(frames[k] - h)) for h in hits}
    durations = []
    for k in range(len(small)):
        ms = max(20, int(round(1000 * steps[k] / fps)))
        durations.append(ms + (int(round(1000 * stop / fps)) if (k in held and stop > 0) else 0))
    small[0].save(gif_path, save_all=True, append_images=small[1:], duration=durations, loop=0, optimize=False)
    picked = tiles[::max(1, every)]
    cols = min(6, len(picked))
    rows = math.ceil(len(picked) / cols)
    tw, th = picked[0].size
    sheet = Image.new("RGB", (cols * tw, rows * th), (235, 236, 240))
    for i, t in enumerate(picked):
        sheet.paste(t, ((i % cols) * tw, (i // cols) * th))
    if sheet.width > 3600:
        k = 3600 / sheet.width
        sheet = sheet.resize((int(sheet.width * k), int(sheet.height * k)))
    sheet_path = os.path.join(out_dir, f"{name}.look.png")
    sheet.save(sheet_path)
    return emit("pass", f"look {name}: {len(frames)} frames x {len(views)} views -> {gif_path} (moving), {sheet_path} (sheet)",
                f"LOOK at {gif_path}: weight, arcs, footwork; the frames in {frames_dir} are files any measure can read",
                gif=gif_path, sheet=sheet_path)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
