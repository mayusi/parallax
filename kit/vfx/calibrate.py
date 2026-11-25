"""calibrate.py — how far the browser player is from Roblox: the same effect, the same camera, both recorded at 24 fps
(the Studio booth: build/vfx/booth/<name>_video/<view>_NNN.png; the player: build/vfx/booth/<name>_play/<view>_NNN.png),
compared as brightness curves, with the ratio per phase so the player's calibration multipliers (CAL in player.js)
can be set from data instead of taste.

    python kit/vfx/calibrate.py <name> [--view cine] [--fps 24] [--sky night|day|overcast|sunset]
    python kit/vfx/calibrate.py fit <name> [--skies night,day,overcast,sunset] [--out assets/effects/_calibrated.json]

Prints a table (time, roblox mean, player mean, ratio) and writes build/vfx/booth/<name>_calibration.json (with --sky:
<name>_calibration_<sky>.json, the CAL the player recorded with kept beside it from <name>_play.metrics.json; refused
unless BOTH recordings were made under that sky: `kit vfx booth <name> --sky <sky>` puts it in <name>.job.json and
`kit vfx play <name> --sky <sky> --record` in the player's metrics). The
ratios that matter: the BASE (no effect: the arena's own brightness), the CHARGE (beams / sprites held for seconds),
the HIT (the peak) and the TAIL (lingering layers). Prints one JSON line last.

FIT (LIMITATIONS_FIXES_V4 Phase 1 item 3: "replace the hand-typed player.js CAL with _calibrated.json"): one
measurement per judging sky -> each multiplier set so the player meets the booth: sprite from the CHARGE ratio, beam
from the HIT, light from the BASE (new = the CAL it was recorded with / its ratio), per sky, and across the skies the
least-squares fit in log space (the geometric mean: a 2x and a 0.5x error weigh the same). Refused while any asked sky
has no measurement - a calibration from one sky is not a calibration.
"""

import glob
import json
import os
import sys

import numpy as np
from PIL import Image


def curve(dirpath, view, fps):
    out = {}
    for f in sorted(glob.glob(os.path.join(dirpath, f"{view}_*.png")) + glob.glob(os.path.join(dirpath, f"{view}_*.jpg"))):
        i = int(f[-7:-4])
        a = np.asarray(Image.open(f).convert("RGB").resize((160, 90))).astype(float)
        out[round((i - 1) / fps, 3)] = float(a.mean())
    return out


def sky_problems(name, sky, booth_dir=os.path.join("build", "vfx", "booth")):
    """a per-sky measurement compares two recordings made under THAT sky: the booth's job (kit vfx booth --sky writes it
    into <name>.job.json) and the player's metrics (kit vfx play --sky: metrics.sky) -> [what does not match]. A
    recording that does not say its sky is not taken for one (a night recording filed as "day" would fit the wrong CAL)"""
    out = []
    for what, path in (("the booth", os.path.join(booth_dir, f"{name}.job.json")),
                       ("the player", os.path.join(booth_dir, f"{name}_play.metrics.json"))):
        try:
            with open(path, encoding="utf-8") as fh:
                said = json.load(fh).get("sky")
        except (OSError, ValueError, AttributeError):
            out.append(f"{what}: no {os.path.basename(path)}")
            continue
        if said is None:
            out.append(f"{what}'s recording does not say its sky ({os.path.basename(path)})")
        elif said != sky:
            out.append(f"{what} recorded under {said}, not {sky}")
    return out


def nearest(c, t):
    k = min(c, key=lambda x: abs(x - t))
    return c[k]


CAL_DEFAULT = {"sprite": 0.4, "beam": 0.7, "light": 18.0}   # player.js CAL_DEFAULT (the hand-set numbers)
SKIES = ("night", "day", "overcast", "sunset")
# which phase each multiplier answers to (calibrate's own phases)
FROM_PHASE = {"sprite": "charge", "beam": "hit", "light": "base"}
SANE = (0.05, 20.0)   # a ratio outside this is a broken recording (a black frame, a missing layer), never a fit


def fit(name, skies, out):
    """the per-sky multipliers and their log-space least-squares fit across skies -> (verdict, code)"""
    import math  # noqa: PLC0415

    per, missing, why = {}, [], []
    for sky in skies:
        path = f"build/vfx/booth/{name}_calibration_{sky}.json"
        try:
            with open(path, encoding="utf-8") as fh:
                m = json.load(fh)
        except (OSError, ValueError):
            missing.append(sky)
            continue
        used = {**CAL_DEFAULT, **{k: v for k, v in (m.get("cal") or {}).items() if k in CAL_DEFAULT}}
        row = {}
        for k, phase in FROM_PHASE.items():
            ph = (m.get("phases") or {}).get(phase)
            r = ph and ph.get("ratio")
            if not isinstance(r, (int, float)) or not SANE[0] <= r <= SANE[1]:
                why.append(f"{sky}: no usable {phase} ratio ({r!r}) for {k}")
                continue
            row[k] = used[k] / r
        per[sky] = row
    if missing or why:
        return {"schema": 1, "status": "fail",
                "summary": "calibrate fit: " + "; ".join(([f"no measurement for {', '.join(missing)}"] if missing else []) + why),
                "next_action": "under each missing sky: record the booth (lune run kit vfx booth <name>) and the player "
                               "(lune run kit vfx play <name> --record), then python kit/vfx/calibrate.py <name> --sky <sky>"}, 1
    allk = {}
    for k in CAL_DEFAULT:
        vals = [per[s][k] for s in skies if k in per[s]]
        allk[k] = round(math.exp(sum(math.log(v) for v in vals) / len(vals)), 4)
    data = {"schema": 1, "name": name, "date": __import__("datetime").date.today().isoformat(),
            "method": "kit/vfx/calibrate.py fit: new = recorded CAL / (player / booth) per phase; across skies the "
                      "least-squares fit in log space (geometric mean)",
            "all": allk, "skies": {s: {k: round(v, 4) for k, v in per[s].items()} for s in skies}}
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
        fh.write("\n")
    return {"schema": 1, "status": "pass",
            "summary": f"calibrate fit {name}: {', '.join(f'{k} {v}' for k, v in allk.items())} across {', '.join(skies)} -> {out}",
            "next_action": "the player loads it on its next bundle (kit vfx play): re-record one sky and re-run "
                           "calibrate.py --sky to see every phase within 35%"}, 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(__doc__)
        return 2
    if argv[0] == "fit":
        if len(argv) < 2:
            print(__doc__)
            return 2
        o = {"--skies": ",".join(SKIES), "--out": os.path.join("assets", "effects", "_calibrated.json")}
        for i in range(2, len(argv) - 1, 2):
            o[argv[i]] = argv[i + 1]
        verdict, code = fit(argv[1], [s for s in o["--skies"].split(",") if s], o["--out"])
        print(json.dumps(verdict))
        return code
    name = argv[0]
    opts = {"--view": "cine", "--fps": "24", "--sky": ""}
    for i in range(1, len(argv) - 1, 2):
        opts[argv[i]] = argv[i + 1]
    view, fps, sky = opts["--view"], int(opts["--fps"]), opts["--sky"]
    if sky and sky not in SKIES:
        print(json.dumps({"schema": 1, "status": "fail", "summary": f"calibrate: --sky {sky} - one of {', '.join(SKIES)}",
                          "next_action": "python kit/vfx/calibrate.py <name> --sky night"}))
        return 2
    if sky:
        wrong = sky_problems(name, sky)
        if wrong:
            print(json.dumps({"schema": 1, "status": "fail", "summary": f"calibrate --sky {sky}: " + "; ".join(wrong),
                              "next_action": f"record both under {sky}: lune run kit vfx booth {name} --sky {sky} and "
                                             f"lune run kit vfx play {name} --sky {sky} --record, then re-run"}))
            return 1
    rb = curve(f"build/vfx/booth/{name}_video", view, fps)
    pl = curve(f"build/vfx/booth/{name}_play", view, fps)
    if not rb or not pl:
        print(json.dumps({"schema": 1, "status": "fail", "summary": f"need both recordings: {name}_video ({len(rb)} frames) and {name}_play ({len(pl)} frames) for view {view}",
                          "next_action": "record both: lune run kit vfx booth <name> (dense --moments) and lune run kit vfx play <name> --record"}))
        return 1
    times = sorted(set(round(t, 2) for t in rb) & set(round(t, 2) for t in pl))
    rows = [(t, nearest(rb, t), nearest(pl, t)) for t in times]
    print("time   roblox  player  ratio")
    for t, a, b in rows[:: max(1, len(rows) // 24)]:
        print(f"{t:5.2f}  {a:6.1f}  {b:6.1f}  {b / max(a, 1):5.2f}")
    peak_t = max(rows, key=lambda r: r[1])[0]
    def phase(lo, hi):
        sel = [(a, b) for t, a, b in rows if lo <= t < hi]
        if not sel:
            return None
        a = sum(x for x, _ in sel) / len(sel)
        b = sum(y for _, y in sel) / len(sel)
        return {"roblox": round(a, 1), "player": round(b, 1), "ratio": round(b / max(a, 1), 2)}
    dur = rows[-1][0]
    phases = {"base": phase(dur - 1.0, dur + 1), "charge": phase(0.8, max(peak_t - 0.4, 0.9)), "hit": phase(peak_t - 0.05, peak_t + 0.3), "tail": phase(peak_t + 0.8, peak_t + 2.5)}
    out = {"name": name, "view": view, "peak_t": peak_t, "phases": phases, "rows": rows}
    # the CAL the player recorded with (its metrics say since 2026-11-20; older: the hand-set numbers)
    try:
        with open(f"build/vfx/booth/{name}_play.metrics.json", encoding="utf-8") as fh:
            met = json.load(fh)
        out["cal"], out["cal_from"] = met.get("cal") or dict(CAL_DEFAULT), met.get("cal_from") or "hand-set (old metrics)"
    except (OSError, ValueError):
        out["cal"], out["cal_from"] = dict(CAL_DEFAULT), "hand-set (no player metrics)"
    if sky:
        out["sky"] = sky
    os.makedirs("build/vfx/booth", exist_ok=True)
    with open(f"build/vfx/booth/{name}_calibration{'_' + sky if sky else ''}.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    worst = max((abs(v["ratio"] - 1), k) for k, v in phases.items() if v)
    print(json.dumps({"schema": 1, "status": "pass" if worst[0] < 0.35 else "fail", "summary": "; ".join(f"{k}: roblox {v['roblox']} vs player {v['player']} (x{v['ratio']})" for k, v in phases.items() if v),
                      "next_action": f"player.js CAL: scale the {worst[1]} phase by 1/{phases[worst[1]]['ratio']} (then re-record and re-run)" if worst[0] >= 0.35 else "within 35% in every phase — the player is a fair preview; the booth stays the truth"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
