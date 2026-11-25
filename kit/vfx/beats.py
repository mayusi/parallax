"""beats.py — give any preset the phase beats the research asks for, at its release moment(s): a short DARK anticipation
beat just before (a screen darkening, 0.05-0.12 s — "felt more than seen") and, ONLY for a truly massive hit, an IMPACT
FRAME on it (--frame white / black / mono, 1-2 frames; default none — owner 2026-10-14: "not everything has to have
impact frames unless ur gonna make it really massive"). What `kit vfx refs timing` flags as missing ("anticipation dip", "snappy climax"), this adds.

    python kit/vfx/beats.py <preset> --release 2.2[,4.95] [--as <new>] [--dip 0.12] [--depth 0.55] [--frame none|white|black|mono]
                                     [--frame-len 0.07]

The original is never touched (default output <preset>_beats). Prints one JSON line. Then record and re-run
`kit vfx refs timing <new>` to see the rules pass.
"""

import copy
import json
import os
import re
import sys


def main(argv):
    if not argv:
        print(json.dumps({"schema": 1, "status": "fail", "summary": "beats: needs a preset and --release <seconds>", "next_action": "python kit/vfx/beats.py <preset> --release 2.2"}))
        return 2
    preset, opts, i = argv[0], {}, 1
    while i < len(argv) - 1:
        opts[argv[i]] = argv[i + 1]
        i += 2
    if "--release" not in opts:
        print(json.dumps({"schema": 1, "status": "fail", "summary": "beats: --release <seconds>[,<seconds>] is required (the climax moment(s))", "next_action": "read it off `kit vfx refs timing`"}))
        return 2
    new = opts.get("--as", f"{preset}_beats")
    if new == preset or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", new):
        print(json.dumps({"schema": 1, "status": "fail", "summary": "beats: --as must be a new valid name", "next_action": "--as <new>"}))
        return 2
    releases = [float(x) for x in opts["--release"].split(",")]
    dip, depth = float(opts.get("--dip", 0.12)), float(opts.get("--depth", 0.55))
    frame, flen = opts.get("--frame", "none"), float(opts.get("--frame-len", 0.07))
    src = json.load(open(os.path.join("assets", "effects", f"{preset}.json"), encoding="utf-8"))
    out = copy.deepcopy(src)
    dur = float(out.get("duration", 0) or 0)
    added = []
    for k, t in enumerate(releases):
        if t - dip < 0 or (dur and t > dur):
            continue
        out["layers"].append({"name": f"beat_dip_{k}", "kind": "screen", "at": round(t - dip, 3), "life": dip,
                              "brightness": [[0, 0], [0.6, -depth], [1, -depth * 0.5]], "saturation": [[0, 0], [1, -0.3]]})
        added.append(f"dip {t - dip:.2f}s")
        if frame != "none":
            out["layers"].append({"name": f"beat_frame_{k}", "kind": "impact", "at": round(t, 3), "life": flen, "mode": frame})
            added.append(f"{frame} frame {t:.2f}s")
    out["about"] = f"{preset} + phase beats (kit/vfx/beats.py: {', '.join(added)}). " + src.get("about", "")
    json.dump(out, open(os.path.join("assets", "effects", f"{new}.json"), "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps({"schema": 1, "status": "pass" if added else "warn", "summary": f"beats {preset} -> {new}: {', '.join(added) or 'nothing (release times out of range)'}",
                      "next_action": f"python kit/vfx/autorec.py {new}; python kit/vfx/refkit.py timing {new}"}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
