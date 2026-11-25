"""studio_calibrate.py - the Roblox-look rig (kit/blender/rbx_lookdev.py) FITTED to Roblox Studio.

    python kit/tools/studio_calibrate.py states <dir> [--names a,b,c]   the shots -> <dir>/states.json
    python kit/tools/studio_calibrate.py fit <dir> [--write]            the fit -> <dir>/fit.json (+ roblox_looks.json)

A calibration run (kit/skills/parallax-3d/reference/10): the grey sphere kit/studio/calib_sphere.py built into
build/_calib and packed (kit/tools/studio_model.py pack _kit_calib_sphere --build build/_calib), its load.luau run in a
kit scratch place, kit/studio/calib_states.luau run with the states while `studio_model.py shot` watches each in turn
(one folder per state, named as the state), and each state's look saved as <dir>/<state>/look.json.

  states  reads every state's shot: the sphere's luminance in Studio (5th, 50th, 95th percentile over its own pixels,
          0-255) and its median colour -> states.json.
  fit     kit/blender/studio_fit.py: the sphere under each state in Blender, for each of Blender's colour curves the
          sun's, the ambient's and the sky's strengths solved, the curve with the least error over every state kept.
          --write records it as roblox_looks.json "_calibration" (with where it was measured and its error): every
          Roblox-look scene and look sheet built after that uses it. Refused when the best fit is off by more than
          FIT_BAR grey levels on average (a bad run must never become the rig).
Prints one JSON line: {status, summary, next_action, ...}."""

import datetime
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import cad_check  # noqa: E402

LOOKS = os.path.join(ROOT, "kit", "blender", "roblox_looks.json")
CALIB = os.path.join("build", "_calib", "models", "_kit_calib_sphere")
FIT_BAR = 6.0          # grey levels (0-255): the most a fit may be off on average, over every state, to be written
STATE_BAR = 15.0       # ... and on any ONE state (review 2026-11-18: a mean hides one realistic state far off)
LUM = (0.2126, 0.7152, 0.0722)


def emit(status, summary, next_action, **extra):
    print(json.dumps({"status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def compact(text):
    """the looks file's own layout: a list of plain numbers on one line ([64, 66, 84]), as it was written by hand"""
    import re  # noqa: PLC0415

    return re.sub(r"\[\s*(-?[\d.eE+-]+(?:,\s*-?[\d.eE+-]+)*)\s*\]",
                  lambda m: "[" + ", ".join(x.strip() for x in m.group(1).split(",")) + "]", text)


def decide(fit_result):
    """a fit -> (written?, why): its curve's mean error within FIT_BAR, its worst state within STATE_BAR, no solved
    number stuck at the end of its search (the light could not reach Studio's value there)"""
    r = fit_result["results"][fit_result["best"]]
    worst = r.get("worst") or {"name": "?", "error": 0.0}
    if r["mean_error"] > FIT_BAR:
        return False, f"{r['mean_error']} grey levels off on average (over {FIT_BAR})"
    if worst["error"] > STATE_BAR:
        return False, f"{worst['name']} is {worst['error']} grey levels off (over {STATE_BAR} on one state)"
    if r.get("at_bound"):
        return False, f"{', '.join(r['at_bound'])} ran into the end of its search: Studio's value was out of reach"
    return True, "within the bars"


def sphere_stats(folder):
    """one state's shot -> the sphere's luminance percentiles and median colour, over the model's own pixels"""
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    v = np.asarray(Image.open(os.path.join(folder, "model.png")).convert("RGB"), float)
    m = np.asarray(Image.open(os.path.join(folder, "mask.png")).convert("L")) > 127
    if m.sum() < 500:
        return None
    lum = v[m] @ np.array(LUM)
    return {"p5": float(np.percentile(lum, 5)), "p50": float(np.percentile(lum, 50)),
            "p95": float(np.percentile(lum, 95)), "rgb50": [float(x) for x in np.percentile(v[m], 50, axis=0)],
            "px": int(m.sum())}


def states(argv):
    folder = os.path.abspath(argv[0])
    names = argv[argv.index("--names") + 1].split(",") if "--names" in argv else sorted(
        d for d in os.listdir(folder) if os.path.isfile(os.path.join(folder, d, "look.json")))
    out, missing = [], []
    for n in names:
        d = os.path.join(folder, n)
        if not all(os.path.isfile(os.path.join(d, f)) for f in ("look.json", "model.png", "mask.png")):
            missing.append(n)
            continue
        st = sphere_stats(d)
        if st is None:
            missing.append(n)
            continue
        with open(os.path.join(d, "look.json"), encoding="utf-8") as fh:
            out.append({"name": n, "look": json.load(fh), "studio": st})
    if missing or not out:
        return emit("fail", f"studio_calibrate states: no complete shot for {missing or 'any state'}",
                    "shoot each state (studio_model.py shot) and save its look.json beside it")
    with open(os.path.join(folder, "states.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    return emit("pass", f"studio_calibrate states: {len(out)} states read", f"python kit/tools/studio_calibrate.py fit {argv[0]}")


def fit(argv):
    folder = os.path.abspath(argv[0])
    st = os.path.join(folder, "states.json")
    blend, manifest = os.path.join(ROOT, CALIB + ".blend"), os.path.join(ROOT, CALIB + ".manifest.json")
    for need in (st, blend, manifest):
        if not os.path.isfile(need):
            return emit("fail", f"studio_calibrate fit: {os.path.relpath(need, ROOT)} missing",
                        "build the sphere (kit/studio/calib_sphere.py) and read the states first")
    out = os.path.join(folder, "fit.json")
    r = subprocess.run([cad_check.blender(), "-b", blend, "--factory-startup", "--python-exit-code", "2", "-P",
                        os.path.join(ROOT, "kit", "blender", "studio_fit.py"), "--", manifest, st, out],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3600)
    line = next((x for x in r.stdout.splitlines() if x.startswith("FIT ")), None)
    if r.returncode != 0 or not line:
        return emit("fail", f"studio_calibrate fit: Blender failed: {(r.stderr or r.stdout)[-400:]}", "read the error")
    with open(out, encoding="utf-8") as fh:
        result = json.load(fh)
    best = result["best"]
    err = result["results"][best]["mean_error"]
    params = result["results"][best]["params"]
    rb = result["results"][best]
    said = (f"{best} fits Studio best, {err} grey levels off on average over {len(rb['states'])} states, "
            f"{rb.get('held_out_error')} on the states it was NOT solved on, the worst "
            f"{(rb.get('worst') or {}).get('name')} {(rb.get('worst') or {}).get('error')} (curves: "
            + ", ".join(f"{t} {r_['mean_error']}" for t, r_ in result["results"].items()) + ")")
    if "--write" not in argv:
        return emit("pass", f"studio_calibrate fit: {said}", f"python kit/tools/studio_calibrate.py fit {argv[0]} --write",
                    best=best, params=params)
    ok, why = decide(result)
    if not ok:
        return emit("fail", f"studio_calibrate fit: {said} - {why}: not written", "look at the states that are off")
    with open(LOOKS, encoding="utf-8") as fh:
        looks = json.load(fh)
    looks["_calibration"] = {
        "about": "the Roblox-look rig fitted to Roblox Studio (kit/tools/studio_calibrate.py): a grey sphere "
                 "(kit/studio/calib_sphere.py) shot in a kit scratch place under each Lighting state, the same sphere "
                 "rendered in Blender, these numbers solved; rbx_lookdev.calibrated_rig + roblox_view use them",
        "measured": datetime.date.today().isoformat(),
        "view_transform": best, **params, "mean_error_grey_levels": err,
        "held_out_error_grey_levels": rb.get("held_out_error"),
        "worst_state": rb.get("worst"),
        "states": [s["name"] for s in result["results"][best]["states"]],
        "not_measured": "the day variant's sun height, ColorShift_Bottom, specular, a place's own Sky (the sky term is "
                        "Roblox's DEFAULT sky's, by day and at night), Atmosphere, bloom and colour grading",
    }
    tmp = LOOKS + ".tmp"           # (written whole, then swapped in: a build reading meanwhile sees old or new)
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(compact(json.dumps(looks, indent=1)) + "\n")
    os.replace(tmp, LOOKS)
    return emit("pass", f"studio_calibrate fit: {said} - written to roblox_looks.json", "re-run a twin to see it hold",
                best=best, params=params)


def main(argv):
    if len(argv) < 2 or argv[0] not in ("states", "fit"):
        return emit("fail", "studio_calibrate: states <dir> | fit <dir> [--write]", "see this file's header")
    return states(argv[1:]) if argv[0] == "states" else fit(argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
