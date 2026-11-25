"""book.py — the STYLE BOOK: every R6 clip measured the same way, beside the owner's verdicts, and what separates
the loved ones from the rejected ones.

    python kit/anim/book.py [--dir build/animations] [--out build/animations/book]
    python kit/anim/book.py --verdict <Name> <loved|good|ok|bad|horrible> "why"

Why (2026-10-11): the owner's eye is the bar ("an amazing running animation" vs "genuinely horrible"), and the kit
kept guessing which numbers matter. The book measures every clip (references and the kit's own) with the same
ruler and joins assets/animations/verdicts.json, so "what makes it good" is read from data:
- kind (locomotion / loop / action), length, frame rate
- KEY DENSITY: keys per second per limb that curve simplification needs (kit/anim/keyreduce.py, 3 deg) - the loved
  sprint's life is in dense limb curves
- SNAPS per second (kit/anim/snaps.py) - single-frame jolts
- BODY DRIVE: the torso's rotation range and travel (big body motion is what reads on R6)
- SPEED: the fastest limb's peak speed per 60th of a second, and its SNAP (peak / mean: hang at the extremes, whip
  through the middle)
- HOLDS: the share of frames where every limb is nearly still (actions: the anticipation / the pose after the hit)
- actions: startup / active / recovery of the fastest limb
Then CALIBRATION: each number's mean for loved + good vs bad + horrible clips, ranked by separation (difference /
pooled spread). With few verdicts it is a hint, said as such - more verdicts make it sharper."""
import glob
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import keyreduce as KR  # noqa: E402
import snaps as SN  # noqa: E402

LIMBS = ("Right Arm", "Left Arm", "Right Leg", "Left Leg")
GOOD = ("loved", "good")
BAD = ("bad", "horrible")


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def measure(clip):
    fps = float(clip.get("fps") or 30)
    loop = bool(clip.get("loop"))
    J = clip["joints"]
    n = len(clip["times"])
    dur = max(float(clip["times"][-1]), 1e-6)
    m = {"kind": "locomotion" if loop and (clip.get("locomotion") or clip.get("priority") == "Movement") else ("loop" if loop else "action"),
         "duration_s": round(dur, 3), "fps": fps}
    red = KR.reduce_clip(clip, 3.0)
    limbs = [j for j in LIMBS if j in J]
    if limbs:
        m["limb keys/s"] = round(float(np.mean([len(red[j]) for j in limbs])) / dur, 1)
    if "Torso" in J:
        m["torso keys/s"] = round(len(red["Torso"]) / dur, 1)
    hits = SN.find(clip)
    m["snaps/s"] = round(sum(len(v) for v in hits.values()) / dur, 2)
    if "Torso" in J:
        F = np.asarray(J["Torso"]["frames"], float)
        q0 = F[0, :4]
        m["torso turn range"] = round(max(KR.qang(q0, f[:4]) for f in F) + 0.0, 1)
        m["torso travel"] = round(float(np.ptp(F[:, 4:7], axis=0).max()), 2)
    sp = {j: SN.speeds(J[j]["frames"], fps, loop) for j in limbs}
    if sp:
        peak_j = max(sp, key=lambda j: sp[j].max())
        s = sp[peak_j]
        m["peak speed"] = round(float(s.max()), 1)
        m["snap"] = round(float(s.max() / max(s.mean(), 1e-6)), 2)
        still = np.all(np.stack([sp[j] < 1.5 for j in limbs]), axis=0)
        m["holds"] = round(float(still.mean()), 2)
        if not loop:
            fast = np.where(s > 0.5 * s.max())[0]
            if len(fast):
                m["startup_s"] = round(fast[0] / fps, 3)
                m["active_s"] = round((fast[-1] - fast[0] + 1) / fps, 3)
                m["recovery_s"] = round(max(0.0, dur - (fast[-1] + 1) / fps), 3)
    return m


def calibrate(rows):
    """within each KIND only (a run against an attack measures the kinds, not the quality)"""
    out = []
    for kind in sorted({r["m"]["kind"] for r in rows}):
        out += calibrate_kind([r for r in rows if r["m"]["kind"] == kind], kind)
    return sorted(out, key=lambda x: -x["separation"])


def calibrate_kind(rows, kind):
    good = [r for r in rows if r.get("verdict") in GOOD]
    bad = [r for r in rows if r.get("verdict") in BAD]
    keys = sorted({k for r in rows for k, v in r["m"].items() if isinstance(v, (int, float)) and k not in ("fps",)})
    out = []
    for k in keys:
        a = [r["m"][k] for r in good if k in r["m"]]
        b = [r["m"][k] for r in bad if k in r["m"]]
        if len(a) < 2 or len(b) < 2:
            continue
        sd = math.sqrt((np.var(a) + np.var(b)) / 2) or 1e-6
        out.append({"kind": kind, "metric": k, "loved/good": round(float(np.mean(a)), 2), "bad/horrible": round(float(np.mean(b)), 2),
                    "separation": round(abs(float(np.mean(a)) - float(np.mean(b))) / sd, 2), "n": [len(a), len(b)]})
    return out


VERDICTS = ("loved", "good", "ok", "bad", "horrible")


def record(name, verdict, note, frame=None, fps=None):
    """the owner's word on a clip (verdicts.json); frame: the FRAME his note is about (kit anim note - dailies with
    frame-accurate notes, AAA plan #8): kept with its time so the dossier gate can quote it"""
    import datetime
    vpath = os.path.join("assets", "animations", "verdicts.json")
    data = json.load(open(vpath, encoding="utf-8")) if os.path.isfile(vpath) else {"about": "owner verdicts", "verdicts": {}}
    entry = {"verdict": verdict, "date": datetime.date.today().isoformat(), "note": note}
    if frame is not None and fps is None:                 # the clip's own rate (a 30 fps clip's frame 18 is 0.6 s)
        cp = os.path.join(os.environ.get("KIT_BUILD", "build"), "animations", f"{name}.clip.json")
        try:
            fps = float(json.load(open(cp, encoding="utf-8")).get("fps") or 60)
        except (OSError, ValueError):
            fps = 60.0
    if frame is not None:
        entry.update(frame=int(frame), t=round(int(frame) / float(fps), 4))
    data["verdicts"].setdefault(name, []).append(entry)
    with open(vpath, "w", encoding="utf-8", newline="") as fh:
        json.dump(data, fh, indent=1)
        fh.write(chr(10))
    return len(data["verdicts"][name])


def main(argv):
    if "--verdict" in argv:
        i = argv.index("--verdict")
        name, verdict = argv[i + 1], argv[i + 2]
        note = argv[i + 3] if len(argv) > i + 3 else ""
        if verdict not in VERDICTS:
            return emit("fail", f"verdict: {verdict!r} is not one of {VERDICTS}", f"lune run kit anim verdict {name} loved 'why'")
        frame = int(argv[argv.index("--frame") + 1]) if "--frame" in argv else None
        k = record(name, verdict, note, frame)
        at = f" at frame {frame}" if frame is not None else ""
        return emit("pass", f"verdict {name}: {verdict}{at} recorded ({k} on file)",
                    "a rejection blocks the rebuild until the dossier answers it (owner_rejections)"
                    if verdict in ("bad", "horrible") else "lune run kit anim book")
    d = argv[argv.index("--dir") + 1] if "--dir" in argv else os.path.join("build", "animations")
    out = argv[argv.index("--out") + 1] if "--out" in argv else os.path.join(d, "book")
    vpath = os.path.join("assets", "animations", "verdicts.json")
    verdicts = json.load(open(vpath, encoding="utf-8"))["verdicts"] if os.path.isfile(vpath) else {}
    rows = []
    for p in sorted(glob.glob(os.path.join(d, "*.clip.json"))):
        name = os.path.basename(p)[: -len(".clip.json")]
        if "." in name:
            continue
        try:
            with open(p, encoding="utf-8") as fh:
                clip = json.load(fh)
        except (OSError, ValueError):
            continue
        if clip.get("rig") != "R6" or not clip.get("joints"):
            continue
        v = verdicts.get(name) or []
        src = (clip.get("source") or {}).get("kind") or ("derived" if clip.get("derived") else "kit")
        m = measure(clip)
        jpath = os.path.join(os.environ.get("KIT_BUILD", "build"), "judge", "anim", name, "verdict.json")
        if os.path.isfile(jpath):
            try:
                jv = json.load(open(jpath, encoding="utf-8"))
                score = jv.get("score") if jv.get("score") is not None else jv.get("overall")
                if isinstance(score, (int, float)):
                    m["judge"] = round(float(score) * (10 if score <= 10 else 1), 1)
            except (OSError, ValueError):
                pass
        rows.append({"name": name, "source": src, "verdict": v[-1]["verdict"] if v else None,
                     "note": v[-1].get("note") if v else None, "m": m})
    cal = calibrate(rows)
    with open(out + ".json", "w", encoding="utf-8") as fh:
        json.dump({"clips": rows, "calibration": cal}, fh, indent=1)
    cols = ["kind", "judge", "duration_s", "limb keys/s", "torso keys/s", "snaps/s", "torso turn range", "torso travel", "peak speed", "snap", "holds", "startup_s", "active_s", "recovery_s"]
    lines = ["# The style book", "", "Every R6 clip measured with one ruler (kit/anim/book.py), with the owner's verdicts "
             "(assets/animations/verdicts.json).", "", "## What separates loved from rejected", "",
             "Compared within one kind only. A kind with fewer than two loved / good AND two bad / horrible clips has no row: "
             "it needs the owner's verdicts first.", "",
             "| kind | metric | loved / good | bad / horrible | separation | n |", "|---|---|---|---|---|---|"]
    kinds_judged = sorted({c["kind"] for c in cal})
    lines += [f"| {c['kind']} | {c['metric']} | {c['loved/good']} | {c['bad/horrible']} | {c['separation']} | {c['n'][0]} / {c['n'][1]} |" for c in cal]
    lines += ["", "## Every clip", "", "| clip | source | verdict | " + " | ".join(cols) + " |", "|" + "---|" * (len(cols) + 3)]
    for r in sorted(rows, key=lambda r: (r["m"]["kind"], r["name"])):
        lines.append(f"| {r['name']} | {r['source']} | {r['verdict'] or ''} | " + " | ".join(str(r["m"].get(c, "")) for c in cols) + " |")
    with open(out + ".md", "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    judged = sum(1 for r in rows if r["verdict"])
    top = "; ".join(f"{c['kind']} {c['metric']} {c['loved/good']} vs {c['bad/horrible']}" for c in cal[:4])
    unjudged = sorted({r["m"]["kind"] for r in rows} - set(kinds_judged))
    return emit("pass", f"book: {len(rows)} R6 clips, {judged} with verdicts -> {out}.md" + (f"; what separates loved from rejected: {top}" if cal else "")
                + (f"; NOT calibrated yet (too few verdicts): {', '.join(unjudged)}" if unjudged else ""),
                f"read {out}.md; record verdicts as the owner gives them: lune run kit anim verdict <Name> <loved|good|ok|bad|horrible> \"why\"",
                calibration=cal[:8])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
