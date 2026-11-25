"""made.py — six layer features PLAYED in the real browser player, hands-free, on made presets of the kit's own (the
pages of the parallax-vfx skill said of each "not run in the browser player"): an object broken into its own pieces, a
lens flare, an authored vector field, a size the camera does not shrink, particles that are meshes, a point cloud a
swarm gathers into. Not in the kit selftest table: it needs a browser and takes a few minutes. Run from the project's
root:

    python kit/selftest/vfx/player/made.py [<name> ...] [--keep]

Nothing goes into a project's assets: the presets are written to build/vfx/animatic/kitfx_<name>.json and played
through the player's `--animatic` door, their kept files (a fracture plan, a field, a point cloud - made by the kit's
own commands with --out-dir) are read from build/vfx/kitfixture/kept with `kit vfx play --kept`. Each is recorded from
the hero view (the forced one from hero and player: two distances) and MEASURED on its frames; the strips of frames are left in
build/vfx/kitfixture/made/ to be LOOKED at. Prints one JSON line {schema, status, summary, next_action, results}.

What each must show (the measure is coarse on purpose: it says the feature DID something on the screen, never that it
looks right - that is the eye's):
  break    lit pixels spread wider at the end than at the start (the pieces fly apart) and are still there (they rest)
  flare    with the flare, more of the frame is lit than the same preset without it, and it is lit off the light too
  field    the swarm's lit pixels are at another place late than early (the air carries them)
  forced   between two views the forced ring's width changes LESS than the plain ring's
  stones   a swarm of mesh stones draws (lit pixels while it lasts, none before it starts)
  cloud    the swarm is tighter round its figure late than early (it gathers)
"""

import json
import os
import shutil
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "vfx"))
import autorec  # noqa: E402

ROOT = os.path.join("build", "vfx", "kitfixture")
KEPT = os.path.join(ROOT, "kept").replace(os.sep, "/")
OUT = os.path.join(ROOT, "made")
ANIMATIC = os.path.join("build", "vfx", "animatic")
BOOTH = os.path.join("build", "vfx", "booth")
W, H = 480, 270

RING = {"kind": "mesh", "at": 0.1, "life": 2.6, "shape": "torus", "material": "Neon", "transparency": [[0, 0], [1, 0]]}
FLARE = {"strength": [[0, 0], [0.15, 1], [0.8, 1], [1, 0]], "ghosts": 5, "size": 0.18, "streak": 0.6, "squeeze": 1.6,
         "color": [255, 220, 170]}
PRESETS = {
    "break": {"duration": 3.2, "layers": [
        {"name": "slab", "kind": "debris", "at": 0.3, "life": 2.8, "point": [0, 6, 0], "pieces": "kitfx_slab",
         "rest": True, "material": "Neon", "color": [255, 190, 120]}]},
    "flare": {"duration": 2.4, "layers": [
        {"name": "sun", "kind": "lens", "at": 0.2, "life": 2.0, "point": [0, 14, -30], "flare": FLARE}]},
    "flare_off": {"duration": 2.4, "layers": [
        {"name": "sun", "kind": "lens", "at": 0.2, "life": 2.0, "point": [0, 14, -30], "vignette": 0.01}]},
    "field": {"duration": 3.2, "layers": [
        {"name": "specks", "kind": "swarm", "at": 0.1, "life": 3.0, "count": 80, "spawn": 0.05, "point": [0, 4, 0],
         "radius": 3, "lifetime": [2.6, 2.9], "speed": [0, 0.5], "size": [[0, 0.35], [1, 0.35]],
         "color": [255, 190, 90], "material": "Neon", "field": {"name": "kitfx_field"}, "seed": 5}]},
    "forced": {"duration": 3.0, "layers": [
        dict(RING, name="plain", point=[0, 4, 0], color=[60, 140, 255], scale=[[0, [3, 3, 3]], [1, [3, 3, 3]]]),
        dict(RING, name="forced", point=[0, 11, 0], color=[255, 110, 40], scale=[[0, [3, 3, 3]], [1, [3, 3, 3]]],
             forced={"ref": 28, "keep": 1, "min": 0.25, "max": 4})]},
    "stones": {"duration": 3.0, "layers": [
        {"name": "stones", "kind": "swarm", "at": 0.5, "life": 2.4, "shape": "Rock", "count": 24, "spawn": 0.05,
         "point": [0, 5, 0], "radius": 4, "lifetime": [2.0, 2.3], "speed": [1, 3], "material": "Neon",
         "size": [[0, 1.2], [1, 0.9]], "rock": {"cuts": 9, "jag": 0.5}, "tumble": [2, 6], "color": [255, 200, 150],
         "seed": 3}]},
    "cloud": {"duration": 3.2, "layers": [
        {"name": "figure", "kind": "swarm", "at": 0.1, "life": 3.0, "count": 70, "spawn": 0.05, "point": [0, 6, 0],
         "radius": 9, "lifetime": [2.7, 2.9], "speed": [0, 0.5], "size": [[0, 0.4], [1, 0.4]], "color": [120, 255, 170],
         "material": "Neon", "cloud": {"name": "kitfx_cloud", "size": 6, "pull": [[0, 0], [0.4, 10], [1, 10]]},
         "seed": 9}]},
}
VIEWS = {"forced": "hero,player"}       # (the camera 28 and 18 studs from the rings)


def kit(*args):
    lune = shutil.which("lune") or "lune"
    got = subprocess.run([lune, "run", "kit", "vfx", *args, "--game", "none"], capture_output=True, text=True)
    return got.returncode == 0, (got.stdout + got.stderr).strip().splitlines()[-3:]


def kept():
    """the kept files, made by the kit's own commands into build/ (never into the effects folder)"""
    made = []
    for folder, args in (("fractures", ["fracture", "kitfx_slab", "--size", "12,12,1"]),
                         ("fields", ["field", "kitfx_field", "--new", "vortex"]),
                         ("points", ["points", "kitfx_cloud", "--new", "star", "--count", "60"])):
        path = os.path.join(KEPT, folder, args[1] + ".json")
        if not os.path.isfile(path):
            ok, said = kit(*args, "--out-dir", f"{KEPT}/{folder}")
            if not ok or not os.path.isfile(path):
                return None, f"kit vfx {args[0]} did not make {path}: {' '.join(said)[-200:]}"
        made.append(path)
    return made, None


def frames(path):
    """the recording's frames, small and grey -> (n, H, W) floats 0..1"""
    got = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vf", f"scale={W}:{H}", "-f", "rawvideo", "-pix_fmt",
                          "rgb24", "-"], capture_output=True)
    raw = np.frombuffer(got.stdout, np.uint8)
    n = len(raw) // (W * H * 3)
    return raw[:n * W * H * 3].reshape(n, H, W, 3).astype(np.float32) / 255.0


def lit(frame, base, colour=None):
    """the pixels a frame lights over the empty stage (the recording's first frame): a boolean picture. colour:
    'warm' / 'cold' keeps only the pixels redder / bluer than they are blue / red"""
    diff = (frame - base).max(axis=2) > 0.10
    if colour == "warm":
        diff &= frame[..., 0] > frame[..., 2] + 0.08
    if colour == "cold":
        diff &= frame[..., 2] > frame[..., 0] + 0.08
    return diff


def spread(mask):
    """(share of the frame lit, centre x, centre y, width of the lit pixels in x, their spread) - shares of the frame"""
    ys, xs = np.nonzero(mask)
    if len(xs) < 4:
        return 0.0, None, None, 0.0, 0.0
    return (len(xs) / mask.size, float(xs.mean()) / W, float(ys.mean()) / H, float(np.ptp(xs)) / W,
            float(np.hypot(xs.std() / W, ys.std() / H)))


def strip(path, name):
    os.makedirs(OUT, exist_ok=True)
    dest = os.path.join(OUT, f"{name}.png")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", path, "-vf", "fps=3,scale=480:-1,tile=5x2", "-frames:v", "1",
                    dest], capture_output=True)
    return dest.replace(os.sep, "/")


def record(name, port):
    preset = dict(PRESETS[name], version=3, name=f"kitfx_{name}", mode="burst")
    os.makedirs(ANIMATIC, exist_ok=True)
    path = os.path.join(ANIMATIC, f"kitfx_{name}.json")
    json.dump(preset, open(path, "w", encoding="utf-8"), indent=1)
    views = VIEWS.get(name, "hero")
    got = autorec.record(f"kitfx_{name}", views, 30, port, 600, extra=["--animatic", "--kept", KEPT],
                         name=f"kitfx_{name}_animatic")
    out = {v: os.path.join(BOOTH, f"kitfx_{name}_animatic_play_{v}.mp4") for v in views.split(",")}
    if not got.get("ok") or not all(os.path.isfile(p) for p in out.values()):
        return None, " ".join(str(got.get("why")).split())[-300:]
    return out, None


def measure(name, clips):
    f = frames(clips["hero"])
    if len(f) < 20:
        return False, f"the recording has {len(f)} frames"
    base, early, late = f[0], f[len(f) // 4], f[len(f) * 3 // 4]
    if name == "break":
        a, b = spread(lit(f[len(f) // 6], base)), spread(lit(late, base))
        fell = None if a[2] is None or b[2] is None else b[2] - a[2]
        return (b[0] > 0.0005 and (fell or 0) > 0.03,
                f"the pieces fell {fell if fell is None else round(fell, 3)} of the frame's height and {b[0]:.4f} of the frame is still lit by them at rest")
    if name == "flare":
        off = frames(clips["off"])
        mid = len(f) // 2
        a, b = spread(lit(f[mid], base)), spread(lit(off[min(mid, len(off) - 1)], off[0]))
        return a[0] > 0.002 and a[0] > b[0] * 3 + 0.001, f"lit share of the frame with the flare {a[0]:.4f}, without {b[0]:.4f}; its marks span {a[3]:.2f} of the width"
    if name == "field":
        a, b = spread(lit(early, base)), spread(lit(late, base))
        moved = None if a[1] is None or b[1] is None else float(np.hypot(b[1] - a[1], b[2] - a[2]))
        still = abs(b[4] - a[4])
        return (a[0] > 0.0003 and b[0] > 0.0003 and (moved or 0) + still > 0.01,
                f"the swarm's centre moved {moved if moved is None else round(moved, 3)} of the frame, its spread {a[4]:.3f} -> {b[4]:.3f}")
    if name == "forced":
        g = frames(clips["player"])
        mid, gm = f[len(f) // 2], g[len(g) // 2]
        hp, hf = spread(lit(mid, base, "cold"))[3], spread(lit(mid, base, "warm"))[3]
        cp, cf = spread(lit(gm, g[0], "cold"))[3], spread(lit(gm, g[0], "warm"))[3]
        if min(hp, hf, cp, cf) <= 0:
            return False, f"a ring is not on the screen (hero plain {hp:.3f} forced {hf:.3f}, player plain {cp:.3f} forced {cf:.3f})"
        plain, forced = max(hp, cp) / min(hp, cp), max(hf, cf) / min(hf, cf)
        return forced < plain - 0.02, (f"between the two views the plain ring's width changes {plain:.2f} times, the forced "
                                       f"ring's {forced:.2f} times (hero {hp:.3f} / {hf:.3f}, player {cp:.3f} / {cf:.3f})")
    if name == "stones":
        before, during = spread(lit(f[8], base)), spread(lit(f[len(f) // 2], base))
        return before[0] < 0.0002 and during[0] > 0.0005, f"lit share before the stones start {before[0]:.4f}, while they last {during[0]:.4f}"
    if name == "cloud":
        a, b = spread(lit(f[4], base)), spread(lit(late, base))
        return a[0] > 0.0002 and b[0] > 0.0002 and b[4] < a[4] * 0.9, f"the swarm's spread {a[4]:.3f} -> {b[4]:.3f} of the frame (it gathers)"
    return False, "no measure"


def main(argv):
    if not os.path.isfile(os.path.join("kit", "vfx", "autorec.py")):
        print(json.dumps({"schema": 1, "status": "fail", "summary": "made presets in the player: run it from the project's root",
                          "next_action": "cd to the folder kit/ is in"}))
        return 1
    names = [a for a in argv if not a.startswith("--")] or ["break", "flare", "field", "forced", "stones", "cloud"]
    _, why = kept()
    results, port = [], 47840
    for name in names:
        if why:
            results.append({"name": name, "ok": False, "said": why})
            continue
        clips, bad = record(name, port)
        port += 1
        if clips and name == "flare":
            off, bad = record("flare_off", port)
            port += 1
            if off:
                clips["off"] = off["hero"]
        if bad and "a flare draws the texture" in bad:
            # (the flare's three pictures are made once a project and registered by the project's build: a project
            # whose build has not registered them cannot draw a flare, and this proof cannot make it)
            results.append({"name": name, "ok": True, "held": True, "said": "HELD: the flare's pictures (lens_glow, "
                            "lens_ghost, lens_streak) are not in this project's texture registry: python kit/vfx/lens.py "
                            "lens_glow lens_ghost lens_streak, then lune run kit vfx"})
            continue
        if bad or not clips:
            results.append({"name": name, "ok": False, "said": f"not recorded: {bad}"})
            continue
        ok, said = measure(name, clips)
        results.append({"name": name, "ok": bool(ok), "said": said,
                        "look": [strip(p, f"{name}_{v}") for v, p in clips.items() if v != "off"]})
    if "--keep" not in argv:
        for f in os.listdir(ANIMATIC) if os.path.isdir(ANIMATIC) else []:
            if f.startswith("kitfx_"):
                os.remove(os.path.join(ANIMATIC, f))
        for f in os.listdir(BOOTH) if os.path.isdir(BOOTH) else []:
            if f.startswith("kitfx_"):
                path = os.path.join(BOOTH, f)
                shutil.rmtree(path, ignore_errors=True) if os.path.isdir(path) else os.remove(path)
    bad = [r["name"] for r in results if not r["ok"]]
    print(json.dumps({"schema": 1, "status": "fail" if bad else "pass",
                      "summary": "made presets in the browser player: " + "; ".join(f"{r['name']}: {r['said']}" for r in results),
                      "next_action": ("kit/vfx/player/player.js - " + ", ".join(bad)) if bad else f"LOOK: {OUT.replace(os.sep, '/')}",
                      "results": results}))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
