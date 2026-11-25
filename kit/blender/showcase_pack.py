"""showcase_pack.py — packs `kit showcase` frames (kit/blender/showcase.py) into what the owner opens:
    turntable.gif   the model turning once
    mechanism.gif   every joint moving in turn (the reload sequence included)
    poster.png      four turntable angles above the key mechanism frames, captioned
System python + Pillow:  python kit/blender/showcase_pack.py build/showcase/<name>
"""

import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

GIF_WIDTH = 640


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def _font(size):
    for f in ("arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            continue
    return ImageFont.load_default()


def gif(folder, names, path, ms):
    frames = []
    for n in names:
        im = Image.open(os.path.join(folder, n)).convert("RGB")
        im = im.resize((GIF_WIDTH, round(im.height * GIF_WIDTH / im.width)), Image.LANCZOS)
        frames.append(im.quantize(colors=255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE))
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=ms, loop=0, optimize=True)
    return os.path.getsize(path)


def poster(folder, info, path):
    turn, mech = info["turntable"], info["mechanism"]
    tiles = [(turn[round(i * len(turn) / 4) % len(turn)], f"{round(i * 360 / 4)} degrees") for i in range(4)] if turn else []
    for m in info.get("joints", []):  # each joint's sequence: its rest, open, and (for a sequence) the next one open
        a, b = m["frames"]
        span = b - a
        picks = [(a + span // 4, f"{m['joint']} opening")]
        if m.get("then"):
            picks.append((a + span // 2, f"{m['joint']} open, {', '.join(m['then'])} moving"))
        else:
            picks.append((a + span // 2, f"{m['joint']} fully open"))
        tiles += [(mech[i], label) for i, label in picks if 0 <= i < len(mech)]
    if not tiles:
        return None
    w = 480
    first = Image.open(os.path.join(folder, tiles[0][0]))
    h = round(first.height * w / first.width)
    cols = 4
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * w, rows * (h + 26)), (14, 15, 17))
    draw = ImageDraw.Draw(sheet)
    font = _font(16)
    for k, (name, label) in enumerate(tiles):
        im = Image.open(os.path.join(folder, name)).convert("RGB").resize((w, h), Image.LANCZOS)
        x, y = (k % cols) * w, (k // cols) * (h + 26)
        sheet.paste(im, (x, y + 26))
        draw.text((x + 8, y + 4), label, fill=(232, 196, 120), font=font)
    sheet.save(path)
    return path


def main(argv):
    if not argv:
        return emit("fail", "showcase pack: no folder given", "python kit/blender/showcase_pack.py build/showcase/<name>")
    folder = argv[0]
    try:
        with open(os.path.join(folder, "showcase.json"), encoding="utf-8") as fh:
            info = json.load(fh)
    except (OSError, ValueError) as e:
        return emit("fail", f"showcase pack: no showcase.json in {folder} ({e})", "run the showcase render first")
    made = []
    if info["turntable"]:
        size = gif(folder, info["turntable"], os.path.join(folder, "turntable.gif"), 90)
        made.append(f"turntable.gif ({size // 1024} KB)")
    if info["mechanism"]:
        size = gif(folder, info["mechanism"], os.path.join(folder, "mechanism.gif"), 70)
        made.append(f"mechanism.gif ({size // 1024} KB)")
    if poster(folder, info, os.path.join(folder, "poster.png")):
        made.append("poster.png")
    return emit("pass", f"showcase {info['asset']}: {', '.join(made)} in {folder}",
                f"open {folder}/poster.png, then the GIFs — the model presented, and its mechanisms moving")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
