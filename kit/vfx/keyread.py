"""keyread.py - the side-by-side QUALITY READ of a test frame against the scene's own key frame (the owner, 2026-11-10,
on flame_arc_keybeat, REDO: "It doesn't look high quality ... It's not there with you know what I'm seeing from
the scene compared to the VFX"). What the scene has at its key beat that ours lacks, as numbers:
  coverage  how much of the frame the effect fills
  light     its white-hot share (the hot core, the light it gives)
  layers    how many luminance bands it spans (dark rim -> body -> bright band -> white core)
  detail    texture energy inside it (torn edges, streaks, flame shapes - not a smooth fill)
  pieces    separate shapes (flame chunks, sparks, embers - density)
Motion is not read here (a still); the recording gate judges it.

    lune run kit vfx keyread <set> --effect <name> [--view hero] [--at <s>]
        the scene's key-beat frame (refs_measured/<set>.chart.json's key beat; the private frames are only measured:
        numbers -> refs_measured/<set>.keyread.json) against the effect's recording at the key beat
        (build/vfx/booth/<name>_play_<view>.mp4 at --at, default the chart's key beat time)
    python kit/vfx/keyread.py --scene-numbers <json> --frame <png>     (a stored scene read against one frame: selftest)
Fails when the effect falls short of the scene on TWO or more of them: under SHORT (0.75) x the scene's coverage, light,
detail or pieces, or two colour bands fewer. Calibrated 2026-11-11 on the owner's verdicts: flame_arc_keybeat (REDO)
read 0.67x coverage, 0.67x light, 0.5x pieces, 0.93x detail of its scene -> 3 gaps, fails; nuke_v4 (8.7) and nuke_v2 (8)
against their real footage read >= 0.87x on every one -> hold. Prints one JSON line {schema, status, summary, next_action}.
"""
import glob
import json
import os
import re
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

REFS = os.path.join("assets", "effects", "refs")
MEASURED = os.path.join("assets", "effects", "refs_measured")
SIZE = (320, 180)
BANDS = [(0, 90), (90, 150), (150, 200), (200, 235), (235, 256)]
SHORT = 0.75  # a gap: ours under this share of the scene's (see the calibration above)


def out(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def local_std(lum):
    from scipy.ndimage import uniform_filter
    m = uniform_filter(lum, 7)
    return np.sqrt(np.clip(uniform_filter(lum * lum, 7) - m * m, 0, None))


def read(img, hue):
    """the five numbers of one frame: the effect = pixels in the set's hue band (coloured fire / energy) or white-hot"""
    im = img.convert("RGB").resize(SIZE)
    rgb = np.asarray(im).astype(float)
    hsv = np.asarray(im.convert("HSV")).astype(float)
    h, s, v = hsv[..., 0] * 360 / 255, hsv[..., 1] / 255, hsv[..., 2] / 255
    lo, hi = hue
    inband = (h >= lo) & (h <= hi) if lo <= hi else (h >= lo) | (h <= hi)
    coloured = inband & (s > 0.25) & (v > 0.35)
    hot = (v > 0.88) & (s < 0.35)
    mask = coloured | hot
    n = int(mask.sum())
    lum = rgb.mean(axis=2)
    from scipy.ndimage import label
    lab, k = label(mask)
    sizes = np.bincount(lab.ravel())[1:] if k else np.array([])
    vals = lum[mask]
    layers = sum(1 for a, b in BANDS if n and ((vals >= a) & (vals < b)).mean() >= 0.04)
    return {"coverage": round(n / mask.size, 4), "light": round(float((hot & mask).sum()) / max(n, 1), 4), "layers": int(layers),
            "detail": round(float(local_std(lum)[mask].mean()) if n else 0.0, 2), "pieces": int((sizes >= 12).sum())}


def compare(scene, ours):
    gaps = []
    for k in ("coverage", "light", "detail", "pieces"):
        if scene[k] > 0 and ours[k] < SHORT * scene[k]:
            gaps.append(f"{k} {ours[k]} vs the scene's {scene[k]} ({scene[k] / max(ours[k], 1e-9):.1f}x)")
    if ours["layers"] <= scene["layers"] - 2:
        gaps.append(f"layers {ours['layers']} vs the scene's {scene['layers']}")
    return gaps


def verdict(scene, ours, what):
    gaps = compare(scene, ours)
    if len(gaps) >= 2:
        return out("fail", f"keyread {what}: short of the scene's key frame on {len(gaps)} of 5 - " + "; ".join(gaps),
                   "build toward what the scene has (more of the frame, a hotter core, more bands, torn detail, more pieces); "
                   "show the owner only when the read holds", scene=scene, ours=ours, gaps=gaps)
    return out("pass", f"keyread {what}: holds beside the scene's key frame" + (f" (one gap: {gaps[0]})" if gaps else ""),
               "show the owner the test frame beside the scene", scene=scene, ours=ours, gaps=gaps)


def frame_at(video, t):
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "f.png")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", video, "-frames:v", "1", p], check=True)
        return Image.open(p).copy()


def scene_key(set_name, measured):
    """the chart's key beat -> its scene frame (the breakdown's f_mm.ss.png nearest the beat's middle)"""
    chart = json.load(open(os.path.join(MEASURED, f"{set_name}.chart.json"), encoding="utf-8"))
    key = next((b for b in chart.get("beats", []) if b.get("key")), None)
    if key is None:
        return None, None, None
    sc = key.get("scene") or [0, 0]
    mid = (sc[0] + sc[1]) / 2
    frames = {}
    for d in (f"{set_name}_scene", measured, set_name):
        for p in glob.glob(os.path.join(REFS, d or "", "f_*.png")):
            m = re.match(r"f_(\d+)\.([\d.]+)\.png$", os.path.basename(p))
            if m:
                frames[int(m.group(1)) * 60 + float(m.group(2))] = p
        if frames:
            break
    if not frames:
        return key, None, None
    best = min(frames, key=lambda k: abs(k - mid))
    return key, frames[best], round(key.get("t", 0) + key.get("len", 0) / 2, 3)


def main(argv):
    opts = dict(zip(argv[::2], argv[1::2])) if len(argv) % 2 == 0 else {}
    if "--scene-numbers" in argv:
        i = argv.index("--scene-numbers")
        sn = json.load(open(argv[i + 1], encoding="utf-8"))
        fr = argv[argv.index("--frame") + 1]
        return verdict(sn["scene"], read(Image.open(fr), tuple(sn["hue"])), f"{os.path.basename(fr)}")
    if not argv or argv[0].startswith("--"):
        return out("fail", "keyread: needs a set", "lune run kit vfx keyread <set> --effect <name> [--view hero] [--at <s>]")
    set_name, rest = argv[0], argv[1:]
    opts = {rest[i]: rest[i + 1] for i in range(0, len(rest) - 1, 2) if rest[i].startswith("--")}
    effect, view = opts.get("--effect"), opts.get("--view", "hero")
    declared = None  # the effect's own measured colours first (hollow_purple_v4 declares "hollow_purple_scene")
    try:
        declared = (json.load(open(os.path.join("assets", "effects", f"{effect}.json"), encoding="utf-8")).get("scene") or {}).get("colours") if effect else None
    except (OSError, ValueError):
        pass
    colours, mpath = None, None
    for c in (declared, f"{set_name}_scene", set_name):
        if c and os.path.isfile(os.path.join(MEASURED, f"{c}.json")):
            colours, mpath = c, os.path.join(MEASURED, f"{c}.json")
            break
    if mpath is None:
        return out("fail", f"keyread {set_name}: no measured colours (its hue band)", f"lune run kit vfx refs measure {set_name}_scene")
    hue = tuple(json.load(open(mpath, encoding="utf-8"))["hue"])
    key, frame, key_t = scene_key(set_name, colours)
    if key is None or frame is None:
        return out("fail", f"keyread {set_name}: no key beat or no scene frame for it", f"lune run kit vfx chart {set_name} --key <beat #>")
    scene = read(Image.open(frame), hue)
    store = {"set": set_name, "hue": list(hue), "key": key.get("beat"), "scene_frame": os.path.basename(frame), "scene": scene}
    json.dump(store, open(os.path.join(MEASURED, f"{set_name}.keyread.json"), "w", encoding="utf-8", newline="\n"), indent=1)
    if not effect:
        return out("pass", f"keyread {set_name}: the scene's key frame read ({scene})", f"lune run kit vfx keyread {set_name} --effect <name>", scene=scene)
    vid = os.path.join("build", "vfx", "booth", f"{effect}_play_{view}.mp4")
    if not os.path.isfile(vid):
        return out("fail", f"keyread {set_name}: no recording {vid}", f"lune run kit vfx play {effect} --record --views {view}")
    t = float(opts.get("--at", key_t))
    return verdict(scene, read(frame_at(vid, t), hue), f"{effect} ({view} @ {t} s) vs {set_name}'s key beat")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
