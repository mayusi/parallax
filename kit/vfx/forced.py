#!/usr/bin/env python3
"""FORCED PERSPECTIVE (the owner's methods list: Forced-perspective effects; the VFX methods audit, stage 13).

In a drawn scene the size of a thing is the DIRECTOR's, not the lens's: a moon that fills the frame from a mile off,
a blade's arc that stays as large on the screen whether the camera is near or far, a far strike drawn bigger than it
could be. A game camera shrinks everything with distance. A mesh layer's `"forced"` block takes that back:

    {"kind": "mesh", ..., "forced": {"ref": 40, "keep": 1, "min": 0.25, "max": 4}}

Every frame the layer's size is multiplied by `scale(distance, forced)`, the distance being from the camera to the
layer's point, in studs:

    (distance / ref) ^ keep, held between min and max

- `ref`: the distance at which the layer is the size it was made at (the multiplier is 1 there).
- `keep` 1 (unless said): the layer holds its ON-SCREEN size (twice as far, twice as large in the world) for as long
  as the multiplier is inside min..max: with the defaults, from a quarter of `ref` to four times it. 0.5: it shrinks with distance, but half as fast as the lens would have it. 0 = off. Negative: it shrinks
  FASTER than the lens (a thing that falls away), down to -1.
- `min`, `max` (0.25 and 4 unless said): the multiplier never leaves these - a camera that flies into the layer does
  not shrink it to nothing, one a mile off does not make it swallow the map.

THE RULE (`scale`; the game's `forcedScale` in src/kit/VfxStage.luau and the player's in kit/vfx/player/player.js
are the same arithmetic, held to it by kit/selftest/vfx/forced/run.py parity). What the parity does NOT compare is
how each side MEASURES the distance and where it applies the multiplier: those were read side by side, not run.

    lune run kit vfx forced [--ref 40] [--keep 1] [--min 0.25] [--max 4] [--at 10,20,40,80,160]

prints the multiplier, and the on-screen size against the size at `ref`, at each distance: read what a `keep` does
before writing it. It writes nothing.

Mesh layers only. A layer held "on twos" (`step`) keeps its size for the whole drawing. An impact frame drawn
through its own camera (`cut`, `subject`) gives the layer the size THAT camera's distance asks. The size is the layer's alone: its place in the world does not move, so a thing made larger also
reaches further (toward the camera too). In the game the camera's place is read in the layer's own update, a frame
behind the picture: on a fast camera the size lags by that frame.
"""
import json
import math
import sys

DEFAULTS = {"keep": 1.0, "min": 0.25, "max": 4.0}


def scale(dist, f):
    """the size multiplier of a forced layer `dist` studs from the camera"""
    ref = f["ref"]
    keep = f.get("keep", 1)
    lo = f.get("min", 0.25)
    hi = f.get("max", 4)
    if not (ref > 1e-6):
        return 1.0
    s = math.pow(max(dist, 1e-3) / ref, keep)
    return max(lo, min(hi, s))


def checked(f):
    """a layer's forced block as the rule reads it; raises ValueError saying what is wrong"""
    def num(v, lo, hi):
        return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and lo <= v <= hi

    if not isinstance(f, dict):
        raise ValueError('forced is a block: {"ref": 40, "keep": 1, "min": 0.25, "max": 4}')
    unread = sorted(set(f) - {"ref", "keep", "min", "max"})
    if unread:
        raise ValueError(f"forced does not read {', '.join(unread)} (it reads ref, keep, min, max)")
    if not num(f.get("ref"), 1, 5000):
        raise ValueError("forced.ref is the distance (1 to 5000 studs) at which the layer is the size it was made at")
    if not num(f.get("keep", 1), -1, 1):
        raise ValueError("forced.keep is -1 to 1 (1 = it holds its size on the screen at any distance, 0 = off)")
    lo, hi = f.get("min", 0.25), f.get("max", 4)
    if not (num(lo, 0.01, 1) and num(hi, 1, 100)):
        raise ValueError("forced.min is 0.01 to 1 and forced.max is 1 to 100 (the multiplier never leaves them)")
    if abs(f.get("keep", 1)) < 0.05:
        raise ValueError("forced.keep nearer 0 than 0.05 does nothing: drop forced")
    if lo == 1 and hi == 1:
        raise ValueError("forced.min 1 and forced.max 1 hold the multiplier at 1: forced does nothing")
    return f


def out(status, summary, next_action, **extra):
    print(json.dumps(dict({"schema": 1, "status": status, "summary": summary, "next_action": next_action}, **extra)))
    return 0 if status == "pass" else 1


def main(argv):
    usage = "lune run kit vfx forced [--ref 40] [--keep 1] [--min 0.25] [--max 4] [--at 10,20,40,80,160]"
    o = {"--ref": "40", "--keep": "1", "--min": "0.25", "--max": "4", "--at": "10,20,40,80,160"}
    i = 0
    while i < len(argv):
        if argv[i] not in o or i + 1 >= len(argv):
            return out("fail", f"forced: {argv[i]} is not an option of it (or has no value)", usage)
        o[argv[i]] = argv[i + 1]
        i += 2
    try:
        f = checked({"ref": float(o["--ref"]), "keep": float(o["--keep"]), "min": float(o["--min"]), "max": float(o["--max"])})
        dists = [float(v) for v in o["--at"].split(",")]
        if not dists or any(not (0 < d <= 100000) for d in dists):
            raise ValueError("--at is distances in studs, above 0, with commas")
    except ValueError as e:
        return out("fail", f"forced: {e}", usage)
    rows = []
    for d in dists:
        s = scale(d, f)
        rows.append({"distance": d, "multiplier": round(s, 3), "on_screen": round(s * f["ref"] / d, 3)})  # (1 = as large on the screen as at ref)
    held = [r for r in rows if abs(r["on_screen"] - 1) < 0.02]
    said = ", ".join(f"{r['distance']:g} studs: x{r['multiplier']:g} (on screen {r['on_screen']:g})" for r in rows)
    return out("pass", f"forced (ref {f['ref']:g}, keep {f['keep']:g}, {f['min']:g} to {f['max']:g}): {said}",
               f"the layer is as large on the screen as at {f['ref']:g} studs at {len(held)} of these {len(rows)} distances; on a mesh layer: "
               f"\"forced\": {json.dumps({k: (int(v) if float(v).is_integer() else v) for k, v in f.items()})}", rows=rows)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
