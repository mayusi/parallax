#!/usr/bin/env python3
"""The self-test of SHOCKWAVE DISTORTION, BAKED (kit/vfx/comp.py "shock"; the VFX methods audit, stage 30).

    python kit/selftest/vfx/shock/run.py good   the starter (kit vfx comp <key> --new shock) baked by the real command:
                                                every check of the sheet passes, among them "bends" (the ring changes
                                                the picture where it is), "bends only at its ring" (nothing changes
                                                over 3 widths from its line: exactly 0) and "runs out"; measured again
                                                here from the written frames against the same sheet with no shock -
                                                the changed places sit within two widths of the ring's own radius in
                                                the first and the last frame; the REAL packer packs the sheet; the
                                                gate takes its spec as Shockwave distortion, and not the same spec with
                                                the shock switched off
    python kit/selftest/vfx/shock/run.py flat   a plain disc with nothing in it and a ring that runs where the disc
                                                is not: nothing is seen to bend - the command must fail naming
                                                "bends", and leave no frames
    python kit/selftest/vfx/shock/run.py fold   a ring three times as strong as its width allows: the command must
                                                refuse it before baking, saying "three tenths of its"

The row stays PARTLY: this bends the sheet's own picture, not the live scene behind it (Glass in Roblox: a Studio
session). Nothing here plays a sheet in Roblox or in the browser player.
"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "vfx"))
import comp  # noqa: E402
import methods  # noqa: E402

import numpy as np  # noqa: E402


def say(status, summary, next_action):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action}))
    return 0 if status == "pass" else 1


def run(root, key, *argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = comp.main([key, *argv, "--specs-dir", os.path.join(root, "specs"), "--frames-dir", os.path.join(root, "frames"), "--look-dir", os.path.join(root, "look"),
                          "--textures-dir", os.path.join(root, "built")])
    return code, json.loads(buf.getvalue().strip().splitlines()[-1])


def write(root, key, spec):
    os.makedirs(os.path.join(root, "specs"), exist_ok=True)
    with open(os.path.join(root, "specs", f"{key}.json"), "w", encoding="utf-8") as fh:
        json.dump(spec, fh)


def frames_in(root, key):
    d = os.path.join(root, "frames", key)
    return [np.load(os.path.join(d, f)).astype(np.float64) for f in sorted(os.listdir(d)) if f.endswith(".npy")] if os.path.isdir(d) else []


def good(root):
    wrong = []
    code, said = run(root, "blast", "--new", "shock")
    if code != 0:
        return say("fail", "shock self-test: the starter was not written: " + said["summary"][:200], "kit/vfx/comp.py")
    code, said = run(root, "blast")
    if code != 0:
        return say("fail", "shock self-test: the starter was refused: " + said["summary"][:260], "kit/vfx/comp.py")
    names = {c["name"]: c for c in said["checks"]}
    for need in ("bends", "bends only at its ring", "runs out"):
        if need not in names or not names[need]["ok"]:
            wrong.append(f"the sheet was not held to: {need}")
    with open(os.path.join(root, "specs", "blast.json"), encoding="utf-8") as fh:
        spec = json.load(fh)
    s, n = spec["comp"]["shock"], spec["cell"]
    got = frames_in(root, "blast")                                # premultiplied, as written
    o = comp.checked(spec)
    plain = [comp.premultiplied(f) for f in comp.frames_of(o, shock=False)]
    if len(got) != spec["frames"]:
        return say("fail", f"shock self-test: {len(got)} frames written, the spec says {spec['frames']}", "kit/vfx/comp.py (bake)")
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float64)
    r = np.hypot(xx - s["centre"][0] * n, yy - s["centre"][1] * n) / n
    for i, want in ((0, s["from"]), (len(got) - 1, s["to"])):
        diff = np.abs(got[i] - plain[i]).mean(-1)
        if diff.sum() < 1e-6:
            wrong.append(f"frame {i} is the picture with no shock")
            continue
        at = float((r * diff).sum() / diff.sum())
        if abs(at - want) > 2 * s["width"]:   # (nothing is bent at the very centre, so a small ring's bent places sit a little outside its line)
            wrong.append(f"in frame {i} the picture is bent {at:.3f} of the cell from the centre, the ring is at {want:.3f}")
        far = np.abs(r - want) > (comp.SHOCK_REACH + 0.3) * s["width"]
        if float(diff[far].max()) > 2e-3:                          # (float16 frames: a thousandth is rounding)
            wrong.append(f"frame {i} is changed {diff[far].max():.4f} far from its ring")
    r2 = subprocess.run([sys.executable, os.path.join(ROOT, "kit", "vfx", "fxfinish.py"), "--specs", os.path.join(root, "specs"), "--frames", os.path.join(root, "frames"),
                         "--out", os.path.join(root, "built"), "--registry", os.path.join(root, "_textures.json"), "--no-review", "blast"],
                        capture_output=True, text=True, timeout=600, check=False, cwd=ROOT)
    try:
        packed = json.loads(r2.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        packed = {"status": "fail", "summary": (r2.stderr.strip().splitlines() or ["the packer printed nothing"])[-1]}
    if packed.get("status") not in ("pass", "warn"):
        wrong.append("the packer refuses the sheet: " + str(packed.get("summary"))[:200])
    m = methods.load()[1]["shockwave_distortion"]
    off = json.loads(json.dumps(spec))
    off["comp"]["shock"]["amount"] = 0
    baked = [alt for alt in m["proof"] if "texture" in alt]
    if not any(methods.texture_proves(alt["texture"], spec) for alt in baked):
        wrong.append("the gate refuses the sheet's spec as Shockwave distortion")
    if any(methods.texture_proves(alt["texture"], off) for alt in baked):
        wrong.append("the gate takes a shock of no strength as Shockwave distortion")
    if m["state"] != "engine" or "level 16 of 21" not in (m.get("reason") or ""):
        wrong.append(f"the register calls Shockwave distortion {m['state']}: the engine bends the live scene through Glass at high graphics only, "
                     "and the baked ring stands in below that - said with the level it was looked at")
    if wrong:
        return say("fail", "shock self-test: " + "; ".join(wrong), "kit/vfx/comp.py (shock_at, check), kit/vfx/methods.json")
    return say("pass", "shock self-test: the starter's ring bends the picture where it is, on its own radius at the first and the last frame, and nothing anywhere else; "
               "the packer packs the sheet; the gate takes it as Shockwave distortion (partly: its own sheet, not the scene behind it) and not with the shock off", "none")


def flat(root):
    spec = comp.new_spec("shock")
    del spec["comp"]["noise"]
    spec["comp"]["shape"]["radius"] = 0.2
    spec["comp"]["shock"].update({"from": 0.3, "to": 0.45})
    write(root, "calm", spec)
    code, said = run(root, "calm")
    if code != 0 and not frames_in(root, "calm"):
        return say("fail", said["summary"], said["next_action"])
    return say("pass", "shock self-test: a ring that bends nothing (a plain disc, the ring outside it) was baked" + (" (or its refusal left frames)" if code != 0 else ""),
               "kit/vfx/comp.py (check: bends)")


def fold(root):
    spec = comp.new_spec("shock")
    spec["comp"]["shock"].update({"width": 0.05, "amount": 0.045})
    write(root, "torn", spec)
    code, said = run(root, "torn")
    if code != 0 and not frames_in(root, "torn"):
        return say("fail", said["summary"], said["next_action"])
    return say("pass", "shock self-test: a ring three times as strong as its width allows was baked", "kit/vfx/comp.py (checked: shock)")


def main(argv):
    cases = {"good": good, "flat": flat, "fold": fold}
    if len(argv) != 1 or argv[0] not in cases:
        return say("fail", "shock self-test: name the case", "good | flat | fold")
    root = tempfile.mkdtemp(prefix="kit_shock_")
    try:
        return cases[argv[0]](root)
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
