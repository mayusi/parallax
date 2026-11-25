"""frames.py — the baked impact frames of a preset become plate textures + a frames map for the game.
    python kit/vfx/frames.py <preset> [view]      (lune run kit vfx play <preset> --frames --views <view> runs it)
Reads build/vfx/booth/<preset>_play/<view>__<layer>.png (the page drew every impact frame layer once, posted with
`tag`), fits each to 1024 wide (16:9), keeps the picture in _downloads/kit_generated/frames/<preset>/<layer>.png
(like every generated source), writes a plate spec assets/textures/frame_<preset>_<layer>.json and the map
assets/effects/frames/<preset>.json = { "<layer>": "frame_<preset>_<layer>" } (Rojo: VfxPresets.frames.<preset>;
Vfx.luau passes it to VfxCompose.expand, which gives each frame layer its `image`). Then `lune run kit vfx` finishes
+ registers the plates and `kit upload --only frame_<preset>_` uploads them.
Honest limit: a baked frame is ONE camera's drawing (the view you baked, `player` by default); every camera in the
game shows that picture. The viewer keeps drawing live from any camera."""
import json
import os
import re
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def main(argv):
    if not argv:
        return emit("fail", "frames.py: needs a preset name", "python kit/vfx/frames.py <preset> [view]")
    preset, view = argv[0], (argv[1] if len(argv) > 1 else "player")
    if not re.fullmatch(r"[A-Za-z0-9_]{1,40}", preset) or not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", view):
        return emit("fail", "frames.py: preset / view names are letters, digits, _", "check the arguments")
    src_dir = os.path.join(ROOT, "build", "vfx", "booth", f"{preset}_play")
    prefix = f"{view}__"
    files = sorted(f for f in os.listdir(src_dir) if f.startswith(prefix)) if os.path.isdir(src_dir) else []
    if not files:
        return emit("fail", f"frames.py: no baked frames in {src_dir} ({prefix}<layer>.png)",
                    f"lune run kit vfx play {preset} --frames --views {view}")
    keep_dir = os.path.join(ROOT, "_downloads", "kit_generated", "frames", preset)
    os.makedirs(keep_dir, exist_ok=True)
    os.makedirs(os.path.join(ROOT, "assets", "effects", "frames"), exist_ok=True)
    frames_map = {}
    written = []
    for f in files:
        layer = os.path.splitext(f[len(prefix):])[0]
        key = "frame_" + preset + "_" + re.sub(r"[^A-Za-z0-9_]+", "_", layer).strip("_").lower()
        im = Image.open(os.path.join(src_dir, f)).convert("RGB")
        if im.width != 1024:
            im = im.resize((1024, max(16, int(round(1024 * im.height / im.width / 8)) * 8)), Image.LANCZOS)
        out_png = os.path.join(keep_dir, f"{layer}.png")
        im.save(out_png)
        rel = os.path.relpath(out_png, ROOT).replace("\\", "/")
        spec = {
            "engine": "fx", "recipe": "import",
            "about": f"{preset} impact frame {layer} — baked from the viewer ({view} camera): the drawn frame the game shows (impact.image via assets/effects/frames/{preset}.json)",
            "pack": "kit baked impact frames (the kit's own drawing of the kit's own effect)",
            "source": rel, "frames": 1, "grid": 1, "cell": 0, "premultiply": True,
            "post": {"alpha": "coverage", "exposure": 1.0}, "plate": True,
        }
        with open(os.path.join(ROOT, "assets", "textures", f"{key}.json"), "w", encoding="utf-8", newline="\n") as fh:
            json.dump(spec, fh, indent=1)
            fh.write("\n")
        frames_map[layer] = key
        written.append(key)
    map_path = os.path.join(ROOT, "assets", "effects", "frames", f"{preset}.json")
    with open(map_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(frames_map, fh, indent=1, sort_keys=True)
        fh.write("\n")
    # one picture to judge: every baked frame in order, with its layer name
    try:
        from PIL import ImageDraw
        thumbs = [(layer, Image.open(os.path.join(keep_dir, f"{layer}.png")).convert("RGB").resize((512, 288), Image.LANCZOS)) for layer in sorted(frames_map)]
        cols = min(4, max(1, len(thumbs)))
        rows = (len(thumbs) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * 512, rows * 304), (24, 24, 28))
        dr = ImageDraw.Draw(sheet)
        for i, (layer, im) in enumerate(thumbs):
            x, y = (i % cols) * 512, (i // cols) * 304
            sheet.paste(im, (x, y))
            dr.text((x + 6, y + 290), layer, fill=(230, 230, 230))
        sheet_path = os.path.join(ROOT, "build", "vfx", "booth", f"{preset}_frames.png")
        sheet.save(sheet_path)
    except Exception as e:  # noqa: BLE001
        sheet_path = f"(no sheet: {e})"
    return emit("pass", f"frames: {len(written)} impact frame(s) of {preset} baked from the {view} camera -> {len(written)} plate spec(s) + assets/effects/frames/{preset}.json; LOOK at build/vfx/booth/{preset}_frames.png",
                f"lune run kit vfx (finish + register), then: lune run kit upload --only frame_{preset}_", textures=written,
                map=os.path.relpath(map_path, ROOT).replace("\\", "/"), sheet=sheet_path.replace("\\", "/") if isinstance(sheet_path, str) else sheet_path)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
