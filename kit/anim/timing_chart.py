"""timing_chart.py — a clip's TIMING CHART (AAA plan #3, board/plans/archive/2026-10-18-aaa-anim-gaps.md: pros map where keys and
breakdowns fall and read the SPACING between them before polishing): speeds of the blade tip and both hands over time
with the move's KEYS, the Hit and any stepped beats marked; below it the classic spacing chart - how far the tip
travels each frame (dense = easing, wide = fast) - and the frame counts between keys.

    python kit/anim/timing_chart.py <clip.json> [--move <move.json>] [--out <png>]

It is a page of every pose sheet (kit/anim/pose_sheet.py pages -> timing.png, the reading in look.json and on the LOOK
line) and its own command (`lune run kit anim timing <Name>`), so the chart is read on every look without asking
(the owner's method lists, 2026-11-13: "timing charts" was a file no command ran).

THE READING (read): the numbers a timing chart is read for, counted from the clip - the frames between the keys, the
frames the strike gathers and cuts in and how long it is quiet after, where the fastest frame sits against each Hit,
and how wide the widest spacing is against the cut's average (1.0 = evenly spaced, the "robot" spacing; a real cut
is uneven). A STEPPED clip is read on its smooth motion (clip.destep: its steps are presentation, and read raw they
make every cut one frame long and evenly spaced); a BLOCKING (held poses, no in-betweens) has no spacing to read and
says so - only the frames between its poses are counted.
They are CAPTIONS, never a gate. Measured on the kit's own fixtures (7 cuts the owner loved, 3 he rejected) the gather
/ cut / quiet counts and the spacing do not tell the two apart. One number does on those ten clips - where the Hit
sits in the clip (loved 0.48-0.55 of its length, rejected 0.34, 0.37, 0.71) - but the loved seven come from two sets
built one way: a rule from that would be a guess, so it is shown and not held.
What DOES fail is a chart drawn against a move that is not the clip's own: the move file names another clip, has no
two timed keys, or its last key is not the clip's last frame (measured on the 124 strike clips built here: 123 end on
their move's last key to the frame; the one that does not is a clip older than its move file)."""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import clip as C  # noqa: E402

QUIET = 0.2          # a frame is "in the strike" while the striker moves at 20% of its fastest or more
LIMB = {"RightHand": "Right Arm", "LeftHand": "Left Arm", "RightFoot": "Right Leg", "LeftFoot": "Left Leg"}
NAME = {"tip": "blade tip", "RightHand": "right hand", "LeftHand": "left hand", "RightFoot": "right foot",
        "LeftFoot": "left foot"}
NOT_ITS_MOVE = "this clip was not built from this move file"


def is_blocking(c):
    return isinstance(c.get("source"), dict) and c["source"].get("kind") == "blocking"


def smooth(c):
    """the clip its spacing is read on: a stepped clip's smooth motion (a blocking stays as it is: it has none)"""
    return c if is_blocking(c) or not c.get("stepped") else C.destep(c)


def clip_fps(c):
    """the clip's frames a second (kit/anim/clip.py clip_fps: what it says, else what its own times say)"""
    return C.clip_fps(c)


def series(c):
    rig = C.load_rig("r6")
    W = C.world_frames(c, rig)
    fps = clip_fps(c)
    t = np.array(c["times"], float)
    end = {k: np.array([(f[p] @ np.array([0.0, -1.0, 0.0, 1.0]))[:3] for f in W]) for k, p in LIMB.items()}
    tip = np.array(c["sword"]["tip"], float) if (c.get("sword") or {}).get("tip") else None
    if tip is not None and len(tip) != len(t):              # a sword track a frame short or long: no tip to chart
        tip = None
    sp = lambda P: np.r_[0.0, np.linalg.norm(np.diff(P, axis=0), axis=1)] * fps
    out = {"t": t, "right_hand": sp(end["RightHand"]), "left_hand": sp(end["LeftHand"]),
           "right_foot": sp(end["RightFoot"]), "left_foot": sp(end["LeftFoot"])}
    if tip is not None:
        out["tip"] = sp(tip)
        out["tip_step"] = np.r_[0.0, np.linalg.norm(np.diff(tip, axis=0), axis=1)]
        out["striker"] = "tip"
    else:                                                    # no blade: the hand or foot that moves fastest strikes
        best = max(LIMB, key=lambda k: float(sp(end[k]).max()))
        out["striker"] = best
    key = {"tip": "tip", "RightHand": "right_hand", "LeftHand": "left_hand", "RightFoot": "right_foot",
           "LeftFoot": "left_foot"}[out["striker"]]
    out["strike"] = out[key]
    out["strike_step"] = out[key] / fps
    return out


def key_times(move):
    """the authored key times of a move file ({"keys": [{"t": ...}]}), or of a plain list of times"""
    if move is None:
        return []
    rows = move.get("keys") if isinstance(move, dict) else move
    out = []
    for k in rows if isinstance(rows, list) else []:
        try:
            out.append(float(k["t"] if isinstance(k, dict) else k))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def strike_at(sp, step, hi, fps):
    """the strike round one Hit (hi, a frame; None = the clip's fastest frame) -> its counts"""
    n = len(sp)
    if hi is not None:
        lo, up = max(0, hi - int(0.4 * fps)), min(n, hi + int(0.15 * fps) + 1)
        pk = lo + int(np.argmax(sp[lo:up]))
    else:
        pk = int(np.argmax(sp))
    peak = float(sp[pk])
    a = pk
    while a > 0 and sp[a - 1] >= QUIET * peak:
        a -= 1
    b = pk
    while b < n - 1 and sp[b + 1] >= QUIET * peak:
        b += 1
    q = a
    while q > 0 and sp[q - 1] < QUIET * peak:
        q -= 1
    r = b
    while r < n - 1 and sp[r + 1] < QUIET * peak:
        r += 1
    seg = step[a:b + 1]
    return {"hit_frame": hi, "peak_frame": pk, "peak_studs_s": round(peak, 1),
            "hit_after_peak_fr": None if hi is None else hi - pk,
            "gather_fr": a - q, "cut_fr": b - a + 1, "quiet_after_fr": r - b, "rise_fr": pk - a, "fall_fr": b - pk,
            "widest_over_mean": round(float(seg.max() / max(float(seg.mean()), 1e-9)), 2),
            "hit_share": None if hi is None else round(hi / max(n - 1, 1), 2)}


def read(c, move=None, marks=None):
    """the chart's numbers -> {fps, frames, seconds, striker, keys, key_frames, key_gaps_fr, the FIRST strike's counts
    (hit_frame, peak_frame, hit_after_peak_fr, gather_fr, cut_fr, quiet_after_fr, rise_fr, fall_fr, widest_over_mean,
    hit_share), strikes: [the same per Hit, in time order], hits_outside, stepped, held, still, mismatch}.
    `mismatch` (a string) says the MOVE's keys are not this clip's: nothing else is then to be trusted against them.
    `marks` = key times that are only marked (a sheet's own key poses, read off this very clip): never a mismatch"""
    if c.get("rig") not in (None, "R6"):
        raise ValueError(f"it is a {c.get('rig')} clip - a timing chart is read on the R6 clip")
    held = is_blocking(c)
    cs = smooth(c)
    s = series(cs)
    fps = clip_fps(c)
    sp, step = s["strike"], s["strike_step"]
    n = len(sp)
    seconds = float(s["t"][-1]) if n else 0.0
    keys = key_times(move) if move is not None else key_times(marks)
    out = {"fps": fps, "frames": n, "seconds": round(seconds, 4), "striker": s["striker"], "keys": len(keys),
           "stepped": bool(c.get("stepped")) and not held}
    if keys:
        fr = [int(round(k * fps)) for k in keys]
        out["key_frames"] = fr
        out["key_gaps_fr"] = [y - x for x, y in zip(fr, fr[1:])]
    if move is not None:
        tol = 1.5 / fps
        theirs = move.get("name") if isinstance(move, dict) else None
        if (isinstance(theirs, str) and isinstance(c.get("name"), str) and theirs != c["name"]
                and not c["name"].startswith(theirs + "_")):         # (a candidate's clip is <Move>_r<round>_c<n>)
            out["mismatch"] = f"the move file is {theirs}'s and the clip is {c['name']}: {NOT_ITS_MOVE}"
        elif len(keys) < 2:
            out["mismatch"] = f"the move file has {len(keys)} timed key(s) - not a move's key list: {NOT_ITS_MOVE}"
        elif keys[0] < -tol or any(y <= x for x, y in zip(keys, keys[1:])):
            out["mismatch"] = f"the keys are not in time order from 0 s - not a move's key list: {NOT_ITS_MOVE}"
        elif abs(keys[-1] - seconds) > tol:
            out["mismatch"] = (f"the last key is at {keys[-1]:.2f} s and the clip ends at {seconds:.2f} s: {NOT_ITS_MOVE} "
                               "(or it is older than the file)")
    if held:
        out["held"] = "held poses (a blocking): no in-betweens, so no spacing to read"
        return out
    if n < 2 or float(sp.max()) <= 1e-6:
        out["still"] = "the clip does not move: there is no spacing to chart"
        return out
    times = sorted(float(e["t"]) for e in c.get("events") or [] if isinstance(e, dict) and e.get("name") == "Hit"
                   and isinstance(e.get("t"), (int, float)))
    inside = [t for t in times if -0.5 / fps <= t <= seconds + 0.5 / fps]
    if len(inside) != len(times):
        out["hits_outside"] = len(times) - len(inside)
    strikes = [strike_at(sp, step, min(n - 1, max(0, int(round(t * fps)))), fps) for t in inside] or [strike_at(sp, step, None, fps)]
    out.update(strikes[0])
    out["strikes"] = strikes
    return out


def hit_words(k):
    d = k["hit_after_peak_fr"]
    return "on the fastest frame" if d == 0 else f"{abs(d)} frame(s) {'after' if d > 0 else 'BEFORE'} the fastest"


def words(r):
    """the reading as one plain line (a sheet's LOOK line, the command's summary)"""
    gaps = ("frames between " + ("poses " if r.get("held") else "keys ") + " | ".join(str(g) for g in r["key_gaps_fr"])
            if r.get("key_gaps_fr") else "")
    if r.get("held"):
        return r["held"] + ("; " + gaps if gaps else "")
    if r.get("still"):
        return r["still"]
    if "cut_fr" not in r:
        return r.get("mismatch") or "nothing to chart"
    who = NAME.get(r.get("striker"), str(r.get("striker")))
    many = len(r.get("strikes") or []) > 1
    text = (f"the {who} gathers {r['gather_fr']} frame(s), cuts in {r['cut_fr']} (fastest at frame {r['peak_frame']}, "
            f"{r['peak_studs_s']} studs/s) and is quiet for {r['quiet_after_fr']} after")
    if r.get("hit_frame") is not None:
        text += f"; the Hit is at frame {r['hit_frame']}, {hit_words(r)}" if not many else \
                f"; Hit 1 of {len(r['strikes'])} is at frame {r['hit_frame']}, {hit_words(r)}"
        for i, k in enumerate(r["strikes"][1:], start=2):
            text += (f"; Hit {i} at frame {k['hit_frame']}, {hit_words(k)} (its cut {k['cut_fr']} frame(s), "
                     f"{k['peak_studs_s']} studs/s)")
    else:
        text += "; no Hit marker"
    if r.get("hits_outside"):
        text += f"; {r['hits_outside']} Hit marker(s) lie outside the clip and are not read"
    text += f"; widest spacing {r['widest_over_mean']}x the cut's average"
    if r.get("stepped"):
        text += " (a stepped clip, read on its smooth motion)"
    if gaps:
        text += "; " + gaps
    return text


def chart(c, move=None, out=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    held = is_blocking(c)
    s = series(smooth(c))
    t = s["t"]
    fps = clip_fps(c)
    keys = key_times(move)
    hits = [float(e["t"]) for e in c.get("events") or [] if isinstance(e, dict) and e.get("name") == "Hit"
            and isinstance(e.get("t"), (int, float)) and -0.5 / fps <= float(e["t"]) <= float(t[-1]) + 0.5 / fps]
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(12, 6.4), sharex=True, gridspec_kw={"height_ratios": [3, 2]})
    for t0, t1, on in c.get("stepped") or []:
        for ax in (a1, a2):
            ax.axvspan(t0, t1, color="#d9e4ff", alpha=0.5, lw=0)
    if "tip" in s:
        a1.plot(t, s["tip"], color="#d4a017", lw=2, label="blade tip")
    a1.plot(t, s["right_hand"], color="#c0392b", lw=1.4, label="right hand")
    a1.plot(t, s["left_hand"], color="#2c5fbf", lw=1.4, label="left hand")
    if s["striker"] in ("RightFoot", "LeftFoot"):
        a1.plot(t, s["strike"], color="#1e8449", lw=2, label=NAME[s["striker"]])
    for i, k in enumerate(keys):
        for ax in (a1, a2):
            ax.axvline(k, color="#555", lw=0.8, ls="--")
        a1.text(k, a1.get_ylim()[1] * 0.97, f"k{i}", fontsize=8, ha="center", va="top")
    for h in hits:
        for ax in (a1, a2):
            ax.axvline(h, color="#e74c3c", lw=2)
        a1.text(h, a1.get_ylim()[1] * 0.88, "HIT", color="#e74c3c", fontsize=9, ha="center", va="top", weight="bold")
    a1.set_ylabel("speed (studs/s)")
    a1.legend(loc="upper left", fontsize=8)
    what = ("HELD POSES (a blocking): each spike is one pose giving way to the next - the rhythm, not a spacing" if held
            else "keys (dashed), Hit (red), stepped beats (shaded; read on the smooth motion)")
    a1.set_title(f"{c.get('name')} timing chart - {what}", fontsize=10)
    a2.bar(t, s["strike_step"], width=0.8 / fps, color="#d4a017" if s["striker"] == "tip" else "#1e8449")
    a2.set_ylabel(f"{NAME.get(s['striker'], s['striker'])} spacing\n(studs / frame)")
    a2.set_xlabel("seconds")
    if len(keys) > 1:
        fr = [int(round(k * fps)) for k in keys]            # the same count as the reading: frame to frame
        gaps = " | ".join(f"k{i}->k{i + 1}: {b - a} fr" for i, (a, b) in enumerate(zip(fr, fr[1:])))
        fig.text(0.01, 0.005, gaps, fontsize=7.5, color="#333")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    out = out or os.path.join("build", "animations", f"{c.get('name')}.timing.png")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    fig.savefig(out, dpi=90)
    plt.close(fig)
    return out


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if not argv:
        print(__doc__)
        return 2

    def say(status, summary, next_action, **extra):
        print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
        return 0 if status == "pass" else 1

    how = "lune run kit anim timing <Name> [--clip <clip.json>] [--move <move.json> | --no-move]"
    try:
        with open(argv[0], encoding="utf-8") as fh:
            c = json.load(fh)
        move = None
        if "--move" in argv:
            with open(argv[argv.index("--move") + 1], encoding="utf-8") as fh:
                move = json.load(fh)
    except (OSError, ValueError, IndexError) as e:
        return say("fail", f"anim timing: a file could not be read ({e})", how)
    if not isinstance(c, dict) or len(c.get("times") or []) < 2 or not isinstance(c.get("joints"), dict):
        return say("fail", f"anim timing: {argv[0]} is not a clip with frames", "lune run kit anim <Name>   (it builds the clip)")
    out = argv[argv.index("--out") + 1] if "--out" in argv and argv.index("--out") + 1 < len(argv) else None
    name = c.get("name")
    try:
        r = read(c, move)
        if r.get("mismatch"):
            return say("fail", f"anim timing {name}: the chart is NOT drawn - {r['mismatch']}",
                       "chart the clip against the move file it was built from (--move <move.json>), or the motion alone "
                       "(--no-move)", reading=r)
        path = chart(c, move, out).replace(os.sep, "/")
    except (ValueError, KeyError, IndexError, TypeError, ZeroDivisionError) as e:
        return say("fail", f"anim timing {name}: the clip cannot be charted ({type(e).__name__}: {e})", how)
    return say("pass", f"anim timing {name}: {path} - {words(r)}",
               f"look at {path}: is the spacing uneven where the cut is (wide bars), dense where it gathers and "
               "settles, and are the frames between the keys the rhythm the move should have?", reading=r, chart=path)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
