"""ground.py — the GAME FRAME a screen is judged over (style frames over gameplay, not a painted gradient).

    python kit/ui/ground.py <identity> <picture> [--ui assets/ui]
    python kit/ui/ground.py <identity> --world <World> [--view eye_2]     (our own world's eye-level look render)

-> assets/ui/grounds/<identity>.png (1920x1080, the picture cropped to cover) + <identity>.json (where it came from).
The preview draws every screen of that identity over it, and the busy-ground contrast check (XAG 102) measures text
against it. It lives OUTSIDE assets/ui/art: a ground is never uploaded. A ground must be a frame WITHOUT another game's
HUD on it (that would be judged as ours): our own worlds' look renders (kit world look) are the default source.
"""
import argparse
import json
import os
import sys
import time

from PIL import Image


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def cover(im, w=1920, h=1080):
    k = max(w / im.width, h / im.height)
    big = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS)
    x, y = (big.width - w) // 2, (big.height - h) // 2
    return big.crop((x, y, x + w, y + h))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("identity")
    ap.add_argument("picture", nargs="?")
    ap.add_argument("--world", default=None, help="one of our worlds: its kit world look render is the ground")
    ap.add_argument("--view", default="eye_1")
    ap.add_argument("--ui", default="assets/ui")
    ap.add_argument("--worlds-look", default="build/worlds/look")
    a = ap.parse_args(argv)
    if not os.path.isfile(os.path.join(a.ui, "identities", f"{a.identity}.json")):
        return emit("fail", f"ground: no identity '{a.identity}'", "lune run kit ui identities (assets/ui/identities/<name>.json)")
    src = a.picture
    if a.world:
        src = os.path.join(a.worlds_look, a.world, f"{a.view}.png")
    if not src or not os.path.isfile(src):
        return emit("fail", f"ground: no picture at {src}", "give a picture, or --world <World> after lune run kit world look <World>")
    im = cover(Image.open(src).convert("RGB"))
    out_dir = os.path.join(a.ui, "grounds")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"{a.identity}.png")
    im.save(out)
    side = {"schema": 1, "identity": a.identity, "source": src.replace("\\", "/"), "world": a.world, "view": a.view if a.world else None,
            "made": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    with open(os.path.join(out_dir, f"{a.identity}.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(side, fh, indent=1)
    return emit("pass", f"ground: {a.identity} screens are judged over {side['source']} (1920x1080 -> {out})",
                f"lune run kit ui   (every {a.identity} screen previews over the game; read its busy_contrast warnings)", file=out.replace("\\", "/"))


if __name__ == "__main__":
    sys.exit(main())
