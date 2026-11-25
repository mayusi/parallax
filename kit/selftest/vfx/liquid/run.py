#!/usr/bin/env python3
"""The self-test of LIQUID, SIMULATED AND BAKED INTO A FLIPBOOK (kit/vfx/liquid.py; the VFX methods audit, stage 25).

    python kit/selftest/vfx/liquid/run.py good   a dam solved by FLIP and a drop solved by the particle fluid, baked by
                                                 the real command: every check of each run passes (no liquid made or
                                                 lost, its energy does not rise, it moves, the picture keeps it, foam
                                                 or spray is made); a still pool stays still under FLIP and a body in
                                                 the air falls as gravity says under both; the REAL packer packs the
                                                 FLIP sheet (1024 px, 64 cells, none empty); the gate takes the FLIP
                                                 sheet as Liquid, FLIP and Foam and spray and NOT as Particle fluid,
                                                 and the other sheet the other way round
    python kit/selftest/vfx/liquid/run.py tall   a dam with a fill of 0.5: the command refuses it in words before
                                                 solving (a dam's fill is 0.42 at most); solved all the same, its
                                                 run-up on the far wall reaches the top of the picture and the check
                                                 of the run must say "under the top of its cell"
    python kit/selftest/vfx/liquid/run.py odd    a sheet of 4 x 4 cells of 100 px: the command must refuse it before solving
                                                 anything, saying a sheet is "256, 512 or 1024" px

The liquid was NEVER matched to a real scene (no clip was read): this holds the physics, not a look.
Nothing here plays a sheet in Roblox or in the browser player.
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
import liquid  # noqa: E402
import methods  # noqa: E402

import numpy as np  # noqa: E402


def say(status, summary, next_action):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action}))
    return 0 if status == "pass" else 1


def bake(root, key, *argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = liquid.main([key, *argv, "--specs-dir", os.path.join(root, "specs"), "--frames-dir", os.path.join(root, "frames"), "--look-dir", os.path.join(root, "look")])
    return code, json.loads(buf.getvalue().strip().splitlines()[-1])


def spec_of(root, key):
    with open(os.path.join(root, "specs", f"{key}.json"), encoding="utf-8") as fh:
        return json.load(fh)


def good(root):
    wrong = []
    g = 4.0
    dt = 1.0 / liquid.rate_of(g)
    # the physics, on made bodies: a still pool, a body in the air
    step = 1.0 / (liquid.NX * liquid.PER)
    xs = (np.arange(liquid.NX * liquid.PER) + 0.5) * step
    x, y = np.meshgrid(xs, xs)
    pts = np.stack([x.reshape(-1), y.reshape(-1)], -1)
    pool = pts[pts[:, 1] < 0.3]
    pos, vel = pool.copy(), pool * 0
    for _ in range(40):
        pos, vel, p, wet = liquid.flip_step(pos, vel, dt, g)
    if float(np.abs(pos - pool).max()) > 1e-6:
        wrong.append(f"a still pool moves by {np.abs(pos - pool).max():.5f} under FLIP")
    if abs(float(p[0].mean()) - g * int(wet[:, 0].sum()) / liquid.NX) > 1e-3:
        wrong.append(f"the pressure at a pool's bed is {p[0].mean():.3f}, gravity x depth is {g * wet[:, 0].sum() / liquid.NX:.3f}")
    blob = pts[(pts[:, 0] - 0.5) ** 2 + (pts[:, 1] - 0.6) ** 2 < 0.01]
    rho0, h = liquid.rest_density()
    for name, stepper in (("FLIP", lambda q, v: liquid.flip_step(q, v, dt, g)[:2]), ("the particle fluid", lambda q, v: liquid.pbf_step(q, v, dt, g, rho0, h)[:2])):
        q, v = blob.copy(), blob * 0
        for _ in range(60):
            q, v = stepper(q, v)
        t = 60 * dt
        fell, want = float(blob[:, 1].mean() - q[:, 1].mean()), 0.5 * g * t * t
        if abs(fell - want) > 0.004:
            wrong.append(f"a body in the air falls {fell:.4f} in {t:.3f} s under {name}, gravity says {want:.4f}")
    # the real command, both solvers
    for key, argv in (("spill", ["--solver", "flip", "--scene", "dam"]), ("plop", ["--solver", "pbf", "--scene", "drop", "--grid", "4", "--cell", "128"])):
        code, said = bake(root, key, *argv)
        if code != 0:
            return say("fail", f"liquid self-test: the {key} was refused: " + said["summary"][:260], "kit/vfx/liquid.py")
        names = [c["name"] for c in said["checks"]]
        for need in ("no liquid is made or lost, none leaves the tank", "the liquid does not gain energy", "the picture keeps its liquid", "foam or spray is made"):
            if need not in names:
                wrong.append(f"the {key}'s run was not held to: {need}")
    # the real packer takes the FLIP sheet
    r = subprocess.run([sys.executable, os.path.join(ROOT, "kit", "vfx", "fxfinish.py"), "--specs", os.path.join(root, "specs"), "--frames", os.path.join(root, "frames"),
                        "--out", os.path.join(root, "built"), "--registry", os.path.join(root, "_textures.json"), "--no-review", "spill"],
                       capture_output=True, text=True, timeout=600, check=False, cwd=ROOT)
    try:
        packed = json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        packed = {"status": "fail", "summary": (r.stderr.strip().splitlines() or ["the packer printed nothing"])[-1]}
    if packed.get("status") not in ("pass", "warn"):
        wrong.append("the packer refuses the FLIP sheet: " + str(packed.get("summary"))[:200])
    else:
        errors = [c["name"] for t in packed.get("textures", []) for c in t.get("checks", []) if not c.get("ok") and c.get("severity") == "error"]
        if errors or not os.path.isfile(os.path.join(root, "built", "spill.png")):
            wrong.append(f"the packed sheet fails {errors}")
    by = methods.load()[1]
    for key, yes, no in (("spill", ("liquid_sim", "flip_fluid", "foam_spray"), ("particle_fluid",)), ("plop", ("liquid_sim", "particle_fluid", "foam_spray"), ("flip_fluid",))):
        spec = spec_of(root, key)
        for m in yes + no:
            got = any(methods.texture_proves(alt["texture"], spec) for alt in by[m]["proof"])
            if got != (m in yes):
                wrong.append(f"the gate {'takes' if got else 'refuses'} the {key} as {by[m]['name']}")
    if wrong:
        return say("fail", "liquid self-test: " + "; ".join(wrong), "kit/vfx/liquid.py, kit/vfx/methods.json")
    return say("pass", "liquid self-test: a still pool stays still, a body falls as gravity says under FLIP and the particle fluid; a dam (FLIP) and a drop (the particle "
               "fluid) bake with every check of their runs, the packer packs the FLIP sheet, and each sheet proves its own solver's method (never matched to a real scene)", "none")


def tall(root):
    # the command refuses such a block in words before solving; the CHECK of the solved picture is what is tried here
    code, said = bake(root, "flood", "--scene", "dam", "--fill", "0.5")
    if code == 0 or "at most for a dam" not in said["summary"] or os.path.exists(os.path.join(root, "specs", "flood.json")):
        return say("pass", "liquid self-test: the command took a dam with a fill of 0.5 (or its refusal wrote a spec): " + said["summary"][:160], "kit/vfx/liquid.py (checked)")
    a = {"solver": "flip", "scene": "dam", "gravity": 4.0, "fill": 0.5, "seed": 1, "fps": 24, "foam": True, "frames": 64, "grid": 8, "cell": 128}
    rows = liquid.solve(a)[2]
    bad = [c for c in rows if not c["ok"]]
    if not bad:
        return say("pass", "liquid self-test: a dam whose run-up reaches the top of the picture passed every check of its run", "kit/vfx/liquid.py (solve)")
    return say("fail", "liquid flood, solved past the command's own refusal: " + "; ".join(f"{c['name']}: {c['value']}" for c in bad), bad[0]["fix"])


def odd(root):
    code, said = bake(root, "six", "--grid", "4", "--cell", "100")
    if code != 0 and not os.path.exists(os.path.join(root, "specs", "six.json")):
        return say("fail", said["summary"], said["next_action"])
    return say("pass", "liquid self-test: a sheet of 4 x 4 cells of 100 px (400 px: the packer refuses it) was baked", "kit/vfx/liquid.py (checked)")


def main(argv):
    cases = {"good": good, "tall": tall, "odd": odd}
    if len(argv) != 1 or argv[0] not in cases:
        return say("fail", "liquid self-test: name the case", "good | tall | odd")
    root = tempfile.mkdtemp(prefix="kit_liquid_")
    try:
        return cases[argv[0]](root)
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
