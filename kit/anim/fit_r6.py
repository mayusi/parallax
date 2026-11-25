"""fit_r6.py — set an R6 gait's parameters from a REFERENCE animation's measured curves.

    python kit/anim/fit_r6.py <Name>.gait.json --to <reference R6 clip.json> [--rounds 6] [--write]

The reference is a finished Roblox R6 animation the owner accepted (kit anim import <file.rbxm> ...). Its per-joint
curves over the cycle (kit/anim/measure.py: pitch / yaw / roll / position, 24 phase samples) are the target; the
gait generator's parameters (kit/anim/gait_r6.py, FIT_RANGES) are moved to minimise the distance (mean absolute
degrees + 30 x studs per joint, after the phase shift that aligns the right legs). The cycle is taken from the
reference outright; the speed stays the spec's (the reference has none: the runtime scales it).

Method: a measured first guess (amplitudes, lean, twist, drop from the reference's own ranges), then coordinate
descent - each parameter tried up and down by a step that halves every round, kept when the distance falls - for
`rounds` rounds. Every candidate is a full generated clip, so the fit is honest about what the generator CAN do;
the residual per joint says what it cannot. --write stores the fitted parameters and `fitted_to` (name, distance,
residual per joint) into the .gait.json; `kit anim <Name>` then builds the fitted clip."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import clip as C         # noqa: E402
import gait_r6 as G      # noqa: E402
import measure as M      # noqa: E402

STEPS = {
    "duty": 0.06, "amp_fwd": 12.0, "amp_back": 12.0, "knee": 0.2, "reach": 0.3, "reach_down": 0.15, "drag": 0.15,
    "overshoot": 3.0, "lean": 5.0, "drop": 0.06, "forward": 0.08, "twist": 5.0, "sway": 2.0, "bob": 0.04, "rise": 0.06,
    "arm_fwd": 25.0, "arm_back": 15.0, "arm_in": 15.0, "arm_out": 15.0, "arm_reach": 0.2, "arm_drop": 0.2, "head": 0.3, "look": 4.0,
}


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def first_guess(p, ref_desc):
    """what the reference's ranges say outright"""
    j, rel = ref_desc["joints"], ref_desc["relations"]
    rl = j.get("Right Leg")
    if rl:
        p["amp_fwd"] = max(20.0, rl["pitch"][1])
        p["amp_back"] = max(20.0, -rl["pitch"][0])
        p["knee"] = max(0.0, rl["pos_y"][1])
        p["reach_down"] = max(0.0, -rl["pos_y"][0])
        p["reach"] = max(0.0, -rl["pos_z"][0])
        p["drag"] = rl["pos_z"][1]
    ra = j.get("Right Arm")
    if ra:
        p["arm_fwd"] = max(0.0, ra["pitch"][1])
        p["arm_back"] = max(-20.0, -ra["pitch"][0])
        p["arm_in"] = (ra["yaw"][1] - ra["yaw"][0]) / 2
        p["arm_out"] = (ra["roll"][1] - ra["roll"][0]) / 2
        p["arm_reach"] = (ra["pos_z"][1] - ra["pos_z"][0]) / 2
        p["arm_drop"] = max(0.0, -ra["pos_y"][0])
    t = j.get("Torso")
    if t:
        p["lean"] = -rel.get("torso_lean_mean", -p["lean"])
        p["twist"] = (t["yaw"][1] - t["yaw"][0]) / 2
        p["sway"] = (t["roll"][1] - t["roll"][0]) / 2
        p["drop"] = -rel.get("torso_drop_mean", -p["drop"])
        p["bob"] = (t["pos_y"][1] - t["pos_y"][0]) / 2
        p["forward"] = -(t["pos_z"][0] + t["pos_z"][1]) / 2
    h = j.get("Head")
    if h and t and abs(p["lean"]) > 1e-6:
        p["head"] = max(0.0, min(1.5, ((h["pitch"][0] + h["pitch"][1]) / 2) / p["lean"]))
    for k, (lo, hi) in G.FIT_RANGES.items():
        if k in p:
            p[k] = float(min(hi, max(lo, p[k])))
    return p


RIG = C.load_rig("r6")


def score(spec, p, ref_cv, fps):
    """the distance of the clip these parameters make - infinite when that clip fails the kit's gates (a fit may
    not buy likeness with skating feet or a snapped loop)"""
    try:
        clip = G.locomotion(p, spec.get("name", "Fit"), fps)
    except Exception:
        return float("inf"), None
    if C.metrics(clip, RIG, spec.get("gate"))["problems"]:
        return float("inf"), None
    cv, _ = M.curves(clip)
    d = M.distance(cv, ref_cv)
    return (d["total"] if d["total"] is not None else float("inf")), d


def fit(spec, ref_clip, rounds=6, log=None):
    kind, p = G.params_of(spec)
    if kind == "idle":
        raise ValueError("an idle is not fitted (its curves are breath)")
    fps = int(spec.get("fps") or 30)
    ref_desc, ref_cv = M.describe(ref_clip)
    p["cycle"] = float(ref_desc["cycle_s"]) if ref_desc["cycle_s"] > 0.05 else p["cycle"]
    guess = first_guess(dict(p), ref_desc)
    best, best_d = score(spec, guess, ref_cv, fps)
    if best < float("inf"):
        p = guess
        if log:
            log(f"first guess: distance {best}")
    else:                                                    # the measured guess fails a gate: start from the kind
        best, best_d = score(spec, p, ref_cv, fps)
        if log:
            log(f"first guess fails the gates; from the defaults: distance {best}")
    steps = dict(STEPS)
    for r in range(rounds):
        improved = False
        for k in list(STEPS):
            if k not in p:
                continue
            lo, hi = G.FIT_RANGES[k]
            for sign in (1.0, -1.0):
                cand = dict(p)
                cand[k] = float(min(hi, max(lo, p[k] + sign * steps[k])))
                if abs(cand[k] - p[k]) < 1e-9:
                    continue
                sc, d = score(spec, cand, ref_cv, fps)
                if sc < best - 1e-6:
                    best, best_d, p = sc, d, cand
                    improved = True
                    break
        if log:
            log(f"round {r + 1}: distance {best}")
        for k in steps:
            steps[k] *= 0.5
        if not improved and r >= 2:
            break
    return p, best, best_d, ref_desc


def main(argv):
    if not argv or "--to" not in argv:
        return emit("fail", "fit_r6: needs <Name>.gait.json --to <reference clip.json> [--rounds N] [--write]", "lune run kit anim fit RunR6 --to CommunitySprint")
    spec_path = argv[0]
    ref_path = argv[argv.index("--to") + 1]
    rounds = int(argv[argv.index("--rounds") + 1]) if "--rounds" in argv else 6
    write = "--write" in argv
    with open(spec_path, encoding="utf-8") as fh:
        spec = json.load(fh)
    with open(ref_path, encoding="utf-8") as fh:
        ref = json.load(fh)
    if ref.get("rig") != "R6":
        return emit("fail", f"fit_r6: {ref_path} is a {ref.get('rig')} clip; the reference must be R6", "import it as it is (kit anim import <file.rbxm> ...)")
    spec["name"] = spec.get("name") or os.path.basename(spec_path).split(".")[0]
    notes = []
    try:
        p, best, best_d, ref_desc = fit(spec, ref, rounds, log=notes.append)
    except ValueError as e:
        return emit("fail", f"fit_r6 {spec['name']}: {e}", f"fix {spec_path}")
    fitted = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in p.items()}
    residual = {k: v["score"] for k, v in (best_d or {}).get("per_joint", {}).items()}
    worst = max(residual, key=residual.get) if residual else None
    if write:
        spec.update(fitted)
        spec["fitted_to"] = {"name": ref.get("name"), "file": ref_path, "distance": best, "residual": residual}
        with open(spec_path, "w", encoding="utf-8", newline="") as fh:
            json.dump(spec, fh, indent=2)
            fh.write("\n")
    return emit("pass", f"fit_r6 {spec['name']} -> {ref.get('name')}: distance {best} ({'; '.join(notes)}); worst joint {worst} {residual.get(worst) if worst else ''}"
                + (f"; written to {spec_path}" if write else " (not written: --write)"),
                f"lune run kit anim {spec['name']} && lune run kit anim look {spec['name']} --rig R6" if write else "re-run with --write to keep it",
                distance=best, residual=residual, params=fitted)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
