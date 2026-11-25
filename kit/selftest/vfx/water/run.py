#!/usr/bin/env python3
"""The self-test of WATER AS A HEIGHT FIELD (kit/vfx/water.py; the VFX methods audit, stage 24).

    python kit/selftest/vfx/water/run.py good     the five recipes baked by the real command. From the BAKED frames:
                                                  a dam's shelf stands at the height Stoker's exact solution gives
                                                  (to 3 %) and its bore is where that solution puts it (to a point and a
                                                  half of the mesh); a looped slosh's last frame steps into its first
                                                  and it is half way round at half its frames; no bake makes or loses
                                                  water. The gate takes a drop, rain and a slosh as Wave simulation and
                                                  a dam and a surge as Shallow-water simulation, and NOT the other way
                                                  round; it refuses a hair bake, a looped dam and a name with no file
    python kit/selftest/vfx/water/run.py edited   a good drop whose every height was made half as tall again by hand:
                                                  the gate must refuse the layer that plays it ("the gate refuses",
                                                  its frames are not what its asks solve to)
    python kit/selftest/vfx/water/run.py fast     a drop asked at a speed its frames cannot show: the command must
                                                  refuse it, saying "flip from frame to frame" (exit 1), writing nothing

The water was NEVER matched to a real scene (no clip was read): this holds the mathematics, not a look.
Nothing here plays a bake in Roblox or in the browser player.
"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "vfx"))
import methods  # noqa: E402
import water  # noqa: E402

import numpy as np  # noqa: E402


def say(status, summary, next_action):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action}))
    return 0 if status == "pass" else 1


def bake(root, name, *argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = water.main([name, *argv, "--out-dir", os.path.join(root, "seq"), "--look-dir", os.path.join(root, "look")])
    return code, json.loads(buf.getvalue().strip().splitlines()[-1])


def read(root, name):
    with open(os.path.join(root, "seq", f"{name}.json"), encoding="utf-8") as fh:
        return json.load(fh)


class NoSpecs:
    def get(self, key):
        return None


def gate(root, method, layer):
    by = methods.load()[1]
    return methods.proved(by[method], [dict({"kind": "mesh", "pivot": "origin", "shape": "seq", "life": 3}, **layer)], NoSpecs(), root, "s") is not None


def heights(d):
    return np.array(d["frames"]).reshape(len(d["frames"]), d["rows"] + 1, d["cols"] + 1, 3)[..., 1]


def good(root):
    wrong = []
    asks = {"drop": [], "rain": ["--recipe", "rain"], "rock": ["--recipe", "slosh", "--frames", "64", "--speed", "0.75", "--loop"],
            "dam": ["--recipe", "dam", "--at", "-0.2", "--frames", "13", "--cols", "24", "--rows", "24"], "surge": ["--recipe", "surge"]}
    for name, argv in asks.items():
        code, said = bake(root, name, *argv)
        if code != 0:
            return say("fail", f"water self-test: the {name} was refused: " + said["summary"][:240], "kit/vfx/water.py")
        d = read(root, name)
        vol = water.volume(heights(d))
        if float(np.abs(vol - vol[0]).max()) > 0.02 * float(np.abs(heights(d)).max()):
            wrong.append(f"the {name} makes or loses water")
    # the dam, from its BAKED mesh: Stoker's shelf and bore half a second after the wall goes
    d = read(root, "dam")
    a = d["args"]
    g = a["speed"] ** 2 / a["depth"]
    shelf, _, bore = water.stoker(a["depth"] * (1 + a["amount"]), a["depth"], g)
    mid = heights(d)[12][12] + a["depth"]
    x = np.arange(25) / 24 - 0.5
    wall = -0.203125                                             # the solver's cell edge the dam stood on
    front = float(x[np.where(mid > (shelf + a["depth"]) / 2)[0].max()])
    if abs(front - (wall + bore * 0.5)) > 1.5 / 24:
        wrong.append(f"the dam's bore is at {front:.3f} after half a second, Stoker's is at {wall + bore * 0.5:.3f}")
    flat = mid[(x > wall + bore * 0.5 - 0.2) & (x < wall + bore * 0.5 - 0.08)]
    if len(flat) < 2 or float(np.abs(flat - shelf).max()) > 0.03 * shelf:
        wrong.append(f"the dam's shelf stands {flat.round(4).tolist()} high, Stoker's is {shelf:.4f}")
    # the slosh: half way round at half its frames (as far down as it was up), and its ends meet
    y = heights(read(root, "rock"))
    left = y[:, 10, 0]
    if abs(left[32] + left[0]) > 0.02 * abs(left[0]) or left[0] == 0:
        wrong.append(f"the slosh's wall stands {left[32]:.4f} at half its frames, it began at {left[0]:.4f}")
    steps = float(np.abs(y[1:] - y[:-1]).max())
    if float(np.abs(y[0] - y[-1]).max()) > 1.5 * steps:
        wrong.append("the looped slosh jumps from its last frame to its first")
    with open(os.path.join(root, "seq", "mane.json"), "w", encoding="utf-8") as fh:
        json.dump(dict(read(root, "drop"), recipe="hair"), fh)
    for what, method, layer, want in (
            ("a drop as Wave simulation", "wave_sim", {"params": {"seq": "drop"}}, True), ("rain as Wave simulation", "wave_sim", {"params": {"seq": "rain"}}, True),
            ("a looped slosh as Wave simulation", "wave_sim", {"params": {"seq": "rock", "loop": True}}, True),
            ("a dam as Shallow-water simulation", "shallow_water", {"params": {"seq": "dam"}}, True),
            ("a surge as Shallow-water simulation", "shallow_water", {"params": {"seq": "surge"}}, True),
            ("a drop as Shallow-water simulation", "shallow_water", {"params": {"seq": "drop"}}, False),
            ("a dam as Wave simulation", "wave_sim", {"params": {"seq": "dam"}}, False),
            ("a looped dam", "shallow_water", {"params": {"seq": "dam", "loop": True}}, False),
            ("a hair bake", "wave_sim", {"params": {"seq": "mane"}}, False), ("a name with no file", "wave_sim", {"params": {"seq": "nothing"}}, False),
            ("a drop on a layer too short to show it", "wave_sim", {"life": 0.2, "params": {"seq": "drop"}}, False)):
        if gate(root, method, layer) != want:
            wrong.append(f"the gate {'refused' if want else 'took'} {what}")
    if wrong:
        return say("fail", "water self-test: " + "; ".join(wrong), "kit/vfx/water.py, kit/vfx/methods.py (kept_file)")
    return say("pass", f"water self-test: five recipes baked; the dam's shelf and bore are Stoker's ({shelf:.4f} high, the bore at {front:.3f}), the slosh is half way round at "
               "half its frames and its ends meet, no water is made or lost; the gate takes waves as Wave simulation and a dam and a surge as Shallow-water simulation and nothing "
               "else (never matched to a real scene)", "none")


def edited(root):
    code, said = bake(root, "drop")
    if code != 0:
        return say("pass", "water self-test: the good drop was refused, so nothing was edited: " + said["summary"][:160], "kit/vfx/water.py")
    took = gate(root, "wave_sim", {"params": {"seq": "drop"}})
    d = read(root, "drop")
    d["frames"] = [[v * 1.5 if k % 3 == 1 else v for k, v in enumerate(f)] for f in d["frames"]]
    with open(os.path.join(root, "seq", "drop.json"), "w", encoding="utf-8") as fh:
        json.dump(d, fh)
    failed = [c for c in water.check(d) if not c["ok"]]
    if took and not gate(root, "wave_sim", {"params": {"seq": "drop"}}) and "the frames are what its asks solve to" in [c["name"] for c in failed]:
        return say("fail", "water self-test: the gate refuses the drop made taller by hand: " + "; ".join(f"{c['name']}: {c['value']}" for c in failed), failed[0]["fix"])
    return say("pass", "water self-test: a drop whose heights were changed by hand still proves Wave simulation", "kit/vfx/water.py (check)")


def fast(root):
    code, said = bake(root, "rush", "--speed", "3", "--fps", "12")
    wrote = os.path.exists(os.path.join(root, "seq", "rush.json"))
    if code != 0 and not wrote:
        return say("fail", said["summary"], said["next_action"])
    return say("pass", "water self-test: a drop whose waves pass a place faster than its frames can show was baked", "kit/vfx/water.py (arguments)")


def main(argv):
    cases = {"good": good, "edited": edited, "fast": fast}
    if len(argv) != 1 or argv[0] not in cases:
        return say("fail", "water self-test: name the case", "good | edited | fast")
    root = tempfile.mkdtemp(prefix="kit_water_")
    try:
        return cases[argv[0]](root)
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
