"""budget.py — WHAT A CLIP COSTS (the owner's older list, AN-40: "evaluate bounded-error curve compression,
distance-based update / animation quality and preload diagnostics ... export size, cold-load latency, pose error
and frame cost meet targets with contact / event timing preserved").

    python kit/anim/budget.py <Name>.clip.json [...]        one clip (or a few)
    python kit/anim/budget.py table <folder of built clips>  every built clip, the costliest first

PER CLIP, off the built files (nothing is built, nothing is uploaded):
  size         the bytes of its exported <Name>.rbxm (what a game ships), and bytes a second of motion
  keys         a joint's turn and its place, once each a frame - what a dense bake writes
  kept         the keys a curve within the kit's own tolerances (0.25 degrees, 0.005 studs: src/kit/AnimCurve thin)
               would keep - the bounded-error compression, by the rule the game's exporter uses
  lost         what the ENGINE's 30-a-second curve playback would drop (degrees, studs: AnimCurve.lost) - the price
               of that compression on a 60-a-second clip (measured in Studio: 5.24 degrees on the loved kesa)
  at events    what a curve animation would be off by at a marker's own frame (a Hit, a Footstep) - the thinning
               AND the engine's 30-a-second grid: a Hit on an odd frame of a 60-a-second clip is not played as keyed
  pops         a joint turning more than 90 degrees between two frames: faster than frames can carry (the build's
               own gate for it is kit/anim/fast_turns.py); its "loss" is counted apart - it is the clip's, not the
               curve's
  stale        the export beside the clip is OLDER than the clip: its bytes are of an earlier build
  moving       the joints that move (a clip that carries 6 joints and moves 2 pays for 6)
THE BARS (the kit's own, off the built clips themselves - no target of the owner's exists yet): a clip is NAMED
when its bytes a second are over 3 times the middle of all built clips, or its export is over BIG bytes. Named,
not failed: a long cutscene is big because it is long.
WHAT ROBLOX DECIDES, and the stand-in: a KeyframeSequence plays every frame exactly and is the size it is; a
CurveAnimation is smaller and is played at 30 samples a second - so the saving is only free for a clip made at 30
a second, or one whose `lost` is under its tolerance. This report says which clips those are.
NOT MEASURED HERE: cold-load latency (the time an uploaded asset takes to arrive: it needs uploaded assets, which
this lane does not make) and the frame cost in a running game (who is animated how often is src/kit/Anim's
budget: board/plans/archive/2026-11-13-anim-methods-audit.md S34)."""
import glob
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
BIG = 150_000        # bytes: an exported clip over this is named
OVER = 3.0           # times the middle bytes-a-second of the built clips
ROT_TOL, POS_TOL = 0.25, 0.005     # (src/kit/AnimCurve ROT_TOL / POS_TOL: said here for the words only)


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def curves(paths, lune="lune"):
    """the curve rule on each clip, by the kit's own Luau (kit/anim/budget_curve.luau) -> {path: row}"""
    out = {}
    if shutil.which(lune) is None:
        raise RuntimeError("lune is not on this machine: the curve rule is the kit's own Luau (src/kit/AnimCurve) and is run through it")
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(0, len(paths), 60):                   # (a command line has a length)
            dst = os.path.join(tmp, f"b{i}.json")
            r = subprocess.run([lune, "run", os.path.join("kit", "anim", "budget_curve.luau"), dst] + paths[i:i + 60],
                               cwd=ROOT, capture_output=True, text=True)
            if r.returncode != 0 or not os.path.isfile(dst):
                raise RuntimeError(f"the curve rule could not be run ({(r.stderr or r.stdout).strip()[:200]})")
            with open(dst, encoding="utf-8") as fh:
                out.update(json.load(fh))
    return out


def row_for(path, curve):
    """one clip's costs -> the row (None: not a clip)"""
    if not isinstance(curve, dict) or curve.get("error") or not curve.get("frames"):
        return None
    with open(path, encoding="utf-8") as fh:
        clip = json.load(fh)
    times = clip.get("times") or [0.0]
    seconds = float(times[-1]) - float(times[0])
    base = path[:-len(".clip.json")]
    rbxm = base + ".rbxm" if os.path.isfile(base + ".rbxm") else None
    size = os.path.getsize(rbxm) if rbxm else None
    stale = bool(rbxm) and os.path.getmtime(rbxm) < os.path.getmtime(path) - 1
    keys, kept = int(curve["keys"]), int(curve["kept"])
    free = curve["lostDeg"] <= ROT_TOL and curve["lostStuds"] <= POS_TOL
    return {"name": clip.get("name") or os.path.basename(base), "seconds": round(seconds, 3), "fps": clip.get("fps"),
            "bytes": size, "bytes_per_s": round(size / seconds) if size and seconds > 1e-3 else None,   # (a one-frame pose has no rate)
            "export_stale": stale, "pops": int(curve.get("pops") or 0), "pop_lost_deg": round(curve.get("popLostDeg") or 0, 1),
            "tracks": curve["tracks"], "moving": curve["moving"], "keys": keys, "kept": kept,
            "kept_share": round(kept / keys, 3) if keys else None,
            "lost_deg": round(curve["lostDeg"], 3), "lost_studs": round(curve["lostStuds"], 4),
            "event_deg": round(curve["eventDeg"], 3), "event_studs": round(curve["eventStuds"], 4),
            "curve_is_free": bool(free)}


def named(rows):
    """the clips over the kit's bars -> ({name: why}, the middle bytes a second)"""
    rates = [r["bytes_per_s"] for r in rows if r["bytes_per_s"]]
    mid = statistics.median(rates) if rates else None
    out = {}
    for r in rows:
        why = []
        if r["bytes"] and r["bytes"] > BIG:
            why.append(f"{r['bytes'] // 1000} KB exported")
        if mid and r["bytes_per_s"] and r["bytes_per_s"] > OVER * mid:
            why.append(f"{r['bytes_per_s'] // 1000} KB a second ({r['bytes_per_s'] / mid:.1f} times the middle clip)")
        if r.get("pops"):
            why.append(f"{r['pops']} frame(s) where a joint turns over 90 degrees: faster than frames can carry")
        if r.get("export_stale"):
            why.append("its export is older than the clip")
        if why:
            out[r["name"]] = "; ".join(why)
    return out, mid


def words(r):
    size = f"{r['bytes'] / 1000:.1f} KB exported ({r['bytes_per_s'] / 1000:.1f} KB a second)" if r["bytes"] else "no export beside it"
    return (f"{r['name']}: {r['seconds']:g} s, {size}; {r['moving']} of {r['tracks']} joints move; a curve would keep "
            f"{r['kept']} of {r['keys']} keys ({100 * r['kept_share']:.0f} in 100) and the engine's 30-a-second playback would lose "
            f"{r['lost_deg']:g} degrees / {r['lost_studs']:g} studs ({r['event_deg']:g} degrees at a marker's frame) "
            + ("- inside the tolerance: the saving is free" if r["curve_is_free"] else "- over the tolerance: it stays a KeyframeSequence"))


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if not argv:
        print(__doc__)
        return 2
    try:
        if argv[0] == "table":
            paths = [p for p in sorted(glob.glob(os.path.join(argv[1], "*.clip.json")))
                     if "." not in os.path.basename(p)[:-len(".clip.json")]]
        else:
            paths = list(argv)
        paths = [os.path.abspath(p) for p in paths]          # (the rule runs from the kit's folder: a path is made whole)
        if not paths:
            return emit("fail", "anim budget: no clip to read", "python kit/anim/budget.py table build/animations")
        cv = curves(paths)
        rows = []
        for p in paths:
            r = row_for(p, cv.get(p))
            if r:
                rows.append(r)
    except RuntimeError as e:
        return emit("fail", f"anim budget: {e}", "install lune (the kit's runner), then run it again")
    except (OSError, ValueError, KeyError, IndexError, TypeError) as e:
        return emit("fail", f"anim budget: it could not be read ({type(e).__name__}: {e})", "python kit/anim/budget.py <clip.json>")
    if not rows:
        return emit("fail", "anim budget: none of them is a clip", "python kit/anim/budget.py <Name>.clip.json")
    if argv[0] != "table":
        return emit("pass", "anim budget: " + " | ".join(words(r) for r in rows[:3]), "none", rows=rows)
    flagged, mid = named(rows)
    sized = [r for r in rows if r["bytes"]]
    total = sum(r["bytes"] for r in sized)
    keys, kept = sum(r["keys"] for r in rows), sum(r["kept"] for r in rows)
    free = [r for r in rows if r["curve_is_free"]]
    fkeys, fkept = sum(r["keys"] for r in free), sum(r["kept"] for r in free)
    hits = [r["event_deg"] for r in rows if not r["curve_is_free"]]
    rows.sort(key=lambda r: -(r["bytes"] or 0))
    return emit("pass", f"anim budget: {len(rows)} built clips; {len(sized)} exported, {total / 1e6:.1f} MB in all, the middle clip "
                + (f"{mid / 1000:.1f} KB a second" if mid else "unsized")
                + f"; a curve within the tolerances would keep {100 * kept / max(keys, 1):.0f} in 100 keys, free of loss on {len(free)} clips "
                f"(there it keeps {100 * fkept / max(fkeys, 1):.0f} in 100); on the others a marker's frame would be off by "
                f"{statistics.median(hits) if hits else 0:.1f} degrees at the middle clip; {len(flagged)} named",
                "look at the named ones; nothing is failed", rows=rows, named=flagged,
                free=[r["name"] for r in free], middle_bytes_per_s=mid)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
