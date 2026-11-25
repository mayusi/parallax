"""refs.py — reference stills for a VFX preset, from anywhere, in one command (and `refs wiki | rank | measure |
compare`: gather whole wiki pages, find the stills that show the effect, measure it, score a render — kit/vfx/refkit.py):

    python kit/vfx/refs.py <preset> <url | file | directory> ... [--frames 6] [--out assets/effects/refs]

Each source becomes still(s) in assets/effects/refs/<preset>/ (git-ignored: copyrighted frames stay private,
measure-only, per the owner's rule): an image file is copied; a GIF or an animated WebP gives `--frames` evenly
spread frames PLUS its brightest frame (the hit); a video (mp4 / webm / mov) gives frames through ffmpeg (every
duration/frames seconds); a directory is scanned for all of these. URLs are fetched with a browser user agent
(wikis refuse plain clients). Every source is appended to SOURCES.md next to the stills (where it came from, when,
what it became) so the judge packet and the viewer's refs panel can say what they show. Prints one JSON line.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request

from PIL import Image, ImageSequence

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36"
IMG = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")
VID = (".mp4", ".webm", ".mov", ".mkv")


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:40] or "ref"


def fetch(url, tmp):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "image/*,video/*,*/*"})
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as fh:
        shutil.copyfileobj(r, fh)
    return tmp


def frames_of_animation(path, base, out, n):
    im = Image.open(path)
    total = getattr(im, "n_frames", 1)
    if total <= 1:
        dst = os.path.join(out, base + ".png")
        im.convert("RGB").save(dst)
        return [dst]
    means = []
    for i, fr in enumerate(ImageSequence.Iterator(im)):
        small = fr.convert("L").resize((32, 18))
        means.append((i, sum(small.get_flattened_data() if hasattr(small, "get_flattened_data") else small.getdata()) / (32 * 18)))
    picks = sorted(set([int(total * k / n) for k in range(n)] + [max(means, key=lambda x: x[1])[0]]))
    made = []
    for k, i in enumerate(picks):
        im.seek(i)
        dst = os.path.join(out, f"{base}_{k:02d}_f{i:03d}.png")
        im.convert("RGB").save(dst)
        made.append(dst)
    return made


def frames_of_video(path, base, out, n):
    made = []
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path], capture_output=True, text=True)
    try:
        dur = float(probe.stdout.strip())
    except ValueError:
        return made
    for k in range(n):
        t = dur * (k + 0.5) / n
        dst = os.path.join(out, f"{base}_{k:02d}_t{t:05.1f}.png")
        r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", path, "-frames:v", "1", dst], capture_output=True)
        if r.returncode == 0 and os.path.isfile(dst):
            made.append(dst)
    return made


def main():
    argv = sys.argv[1:]
    if argv and argv[0] in ("wiki", "rank", "measure", "compare", "timing", "norms", "lore", "brief", "silhouette"):  # gather at scale / understand / compare (refkit.py)
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import refkit  # noqa: E402

        return refkit.main(argv)
    if len(argv) < 2:
        print(json.dumps({"schema": 1, "status": "fail", "summary": "vfx refs: needs a preset and at least one source (url | file | directory)",
                          "next_action": 'lune run kit vfx refs <preset> "https://…/still.jpg" clip.gif frames/ (GIF / WebP / video become frames; sources logged in SOURCES.md)'}))
        return 2
    preset = argv[0]
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", preset):
        print(json.dumps({"schema": 1, "status": "fail", "summary": f"bad preset name {preset!r}: letters, digits, _ and - only", "next_action": "lune run kit vfx refs <preset> <url|file>..."}))
        return 2
    opts = {"--frames": "6", "--out": os.path.join("assets", "effects", "refs")}
    sources, i = [], 1
    while i < len(argv):
        if argv[i].startswith("--") and i + 1 < len(argv):
            opts[argv[i]] = argv[i + 1]
            i += 2
        else:
            sources.append(argv[i])
            i += 1
    n = int(opts["--frames"])
    out = os.path.join(opts["--out"], preset)
    os.makedirs(out, exist_ok=True)
    raw = os.path.join(out, "raw")
    os.makedirs(raw, exist_ok=True)
    log, made, errors = [], [], []
    todo = []
    for src in sources:
        if os.path.isdir(src):
            todo += [os.path.join(src, f) for f in sorted(os.listdir(src)) if f.lower().endswith(IMG + VID)]
        else:
            todo.append(src)
    for src in todo:
        try:
            is_url = src.startswith(("http://", "https://"))
            ext = os.path.splitext(src.split("?")[0].rstrip("/"))[1].lower()
            if is_url and ext not in IMG + VID:
                ext = ".gif" if "gif" in src.lower() else ".jpg"
            base = slug(os.path.splitext(os.path.basename(src.split("?")[0].rstrip("/")))[0])
            local = os.path.join(raw, base + ext)
            if is_url:
                fetch(src, local)
            else:
                shutil.copyfile(src, local)
            if ext in VID:
                stills = frames_of_video(local, base, out, n)
            else:
                stills = frames_of_animation(local, base, out, n)
            made += stills
            log.append(f"| {time.strftime('%Y-%m-%d')} | {src} | {os.path.getsize(local):,} B | {len(stills)} still(s): {', '.join(os.path.basename(s) for s in stills[:3])}{'…' if len(stills) > 3 else ''} |")
        except Exception as e:  # noqa: BLE001
            errors.append(f"{src}: {type(e).__name__}: {e}")
    src_md = os.path.join(out, "SOURCES.md")
    new = not os.path.isfile(src_md)
    with open(src_md, "a", encoding="utf-8", newline="\n") as fh:
        if new:
            fh.write(f"# Reference sources — {preset}\n\nPrivate, measure-only reference material (copyrighted frames are never redistributed; this folder is git-ignored).\n\n| date | source | size | became |\n|---|---|---|---|\n")
        for line in log:
            fh.write(line + "\n")
    status = "pass" if made and not errors else ("fail" if not made else "pass")
    print(json.dumps({"schema": 1, "status": status, "summary": f"{len(made)} still(s) from {len(todo) - len(errors)}/{len(todo)} source(s) -> {out.replace(os.sep, '/')}" + (f"; errors: {'; '.join(errors)[:300]}" if errors else ""),
                      "next_action": f"LOOK at them (the viewer's refs panel: lune run kit vfx play {preset}); the judge packet picks them up: lune run kit vfx judge {preset}", "stills": [m.replace(os.sep, "/") for m in made]}))
    return 0 if status == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
