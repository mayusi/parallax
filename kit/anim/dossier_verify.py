"""dossier_verify.py — the VERIFIER (mission 04-anim 5.11; research: VIGA 2026 - compare against the reference per
region, ONE difference + ONE edit, never a score; scored judges plateaued and contradicted the owner by 1-2 points).
A clip is measured against its move dossier's numeric checks (proc_dossier.check), phase by phase in the order the
move happens; the report names the ONE difference that matters most (the first failing check in move order, or - when
all pass - the check closest to its edge) and the ONE edit that moves it (the dossier's check -> build key -> field,
and which way). When every check passes it says so and hands the look to the owner's eye: numbers are not poses.
    python kit/anim/dossier_verify.py <clip.json | Name> [--dossier <move>]"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import proc_dossier as DS  # noqa: E402

# the move's order of events (a check's place in time) - phases a check belongs to
ORDER = ["windup", "windup_time", "swing_time", "hip_leads", "snap_hips", "snap_leg", "pivot", "hips_over", "lean_away",
         "rib_height", "rise", "arm_swing", "guard_up", "eyes", "through", "hold_extreme", "no_slide", "recoil_long"]


def margin(v, rg):
    """how deep inside (+) or outside (-) its range a value sits, in range widths"""
    lo, hi = rg
    w = max(hi - lo, 1e-6)
    if lo == 0 and v >= 0:                       # a one-sided range (a drift, a slide): 0 is perfect, not an edge
        return (hi - v) / w
    return min(v - lo, hi - v) / w


def verify(c, d, ranges=None, report_only=()):
    """report_only: checks reported but not failed (a prior upper body is not held to the Thai arm technique)"""
    res = DS.check(c, d, ranges)["checks"]
    by = {ck["id"]: ck for ck in d["checks"]}
    order = sorted(res, key=lambda k: ORDER.index(k) if k in ORDER else len(ORDER))
    failing = [k for k in order if not res[k]["pass"] and k not in report_only]
    k = failing[0] if failing else min((x for x in order if x not in report_only), key=lambda x: margin(res[x]["value"], res[x]["range"]))
    r, ck = res[k], by[k]
    lo, hi = r["range"]
    v = r["value"]
    edit = ck.get("edit")
    if edit and "to" in edit:                                         # a DIRECTION check (lower is closer): no raise/lower
        how = f"move {edit['key']}.{edit['field']} toward {edit['to']}" + (f" ({edit['note']})" if edit.get("note") else "")
    elif edit:
        up = v < lo if not r["pass"] else (v - lo) < (hi - v)      # outside low / nearer the low edge -> raise it
        direction = "raise" if up == (edit.get("sign", 1) > 0) else "lower"
        how = f"{direction} {edit['key']}.{edit['field']}" + (f" ({edit['note']})" if edit.get("note") else "")
    else:
        how = "no edit mapped for this check - add one to the dossier (checks[].edit: key, field, sign)"
    return {"difference": f"{k}: {v} {'outside' if not r['pass'] else 'inside, closest to the edge of'} {r['range']} - {r['why']}",
            "edit": how, "check": k, "failing": failing, "all_pass": not failing,
            "report_only": {x: res[x]["value"] for x in report_only if x in res and not res[x]["pass"]}}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    a = sys.argv[1:]
    src = a[0]
    path = src if os.path.isfile(src) else next(
        (p for p in (os.path.join("build", "animations", f"{src}.r6.clip.json"), os.path.join("build", "animations", f"{src}.clip.json"))
         if os.path.isfile(p)), None)
    if path is None:
        print(json.dumps({"schema": 1, "status": "fail", "summary": f"no built clip for {src}", "next_action": f"lune run kit anim {src}"}))
        sys.exit(1)
    c = json.load(open(path, encoding="utf-8"))
    stem = os.path.basename(src).split(".")[0] if os.path.isfile(src) else src
    move = a[a.index("--dossier") + 1] if "--dossier" in a else c.get("dossier") or DS.snake(stem)
    try:
        d = DS.require(move)
    except SystemExit as e:
        print(json.dumps({"schema": 1, "status": "fail", "summary": f"{src}: {e}",
                          "next_action": f"a clip is verified against its move dossier: lune run kit anim dossier new {move}"}))
        sys.exit(1)
    skip = ()
    if "candidate" in c and d["build"].get("builder") == "proc_kick":
        # a candidate's own build (its sliders moved the keys the checks read)
        import proc_candidates as PCA
        import proc_kick as PK
        s = c["candidate"]["sliders"]
        d = {**d, "build": {**d["build"], "keys": PCA.apply_sliders(PK.carry(d["build"]["keys"]), s)}}
        if s.get("arms", "technique") != "technique":
            skip = PCA.TECHNIQUE_ARM_CHECKS
    r = verify(c, d, report_only=skip)
    print(json.dumps({"schema": 1, "status": "pass" if r["all_pass"] else "fail",
                      "summary": f"vs dossier {move}: " + (f"{len(r['failing'])} difference(s); the first in the move's order: {r['difference']}"
                                                           if not r["all_pass"] else f"no difference outside the dossier; closest call: {r['difference']}"),
                      "next_action": (f"improve: {r['edit']}" if not r["all_pass"]
                                      else "look at it: the numbers match the dossier, the POSE is the owner's eye (kit anim picks)"),
                      "failing": r["failing"], "report_only": r["report_only"]}))
    sys.exit(0 if r["all_pass"] else 1)
