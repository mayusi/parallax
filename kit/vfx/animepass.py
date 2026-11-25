"""animepass.py — the anime/stylized pass on any preset (research 2026-10-14: stylized VFX animate on TWOS — 12 drawings a
second — and DISSOLVE through a noise mask instead of fading; the Panda team "avoided a simple opacity fade";
Riot: a short, low-contrast dissipation). For every MESH layer:
  - step: 12 (its clock held on drawings: wobble, scroll, scale, colour all move on twos)
  - a fade-out at the end of its life becomes an EROSION: erode [start, 1, soft] from where the fade began, and the
    transparency holds its value through that stretch (the dissolve does the vanishing, patch by patch, tips first)

    python kit/vfx/animepass.py <preset> [--as <new>] [--step 12] [--soft 0.18] [--min-fade 0.12]

The original is never touched (default output <preset>_anime). Prints one JSON line.
"""

import copy
import json
import os
import re
import sys


def fade_start(tr):
    """where the final fade to 1 begins (life fraction), or None when the layer does not fade out at its end"""
    if not (isinstance(tr, list) and len(tr) >= 2 and isinstance(tr[0], list)):
        return None
    last = tr[-1]
    if last[1] < 0.98:
        return None
    for i in range(len(tr) - 2, -1, -1):
        if tr[i][1] < 0.9:
            return tr[i][0], tr[i][1], i
    return None


def main(argv):
    if not argv:
        print(json.dumps({"schema": 1, "status": "fail", "summary": "animepass: needs a preset", "next_action": "python kit/vfx/animepass.py <preset>"}))
        return 2
    preset, opts, i = argv[0], {}, 1
    while i < len(argv) - 1:
        opts[argv[i]] = argv[i + 1]
        i += 2
    new = opts.get("--as", f"{preset}_anime")
    if new == preset or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", new):
        print(json.dumps({"schema": 1, "status": "fail", "summary": "animepass: --as must be a new valid name", "next_action": "--as <new>"}))
        return 2
    step, soft, min_fade = float(opts.get("--step", 12)), float(opts.get("--soft", 0.18)), float(opts.get("--min-fade", 0.12))
    src = json.load(open(os.path.join("assets", "effects", f"{preset}.json"), encoding="utf-8"))
    out = copy.deepcopy(src)
    stepped = eroded = 0
    for el in out.get("layers", []):
        if el.get("kind") != "mesh":
            continue
        if not el.get("flipbook"):  # a flipbook already steps on its own fps
            el["step"] = step
            stepped += 1
        f = fade_start(el.get("transparency"))
        if f and el.get("erode") is None and el.get("shape") not in ("Ball", "Block", "Cylinder"):  # primitives have no vertices
            t0, v0, idx = f
            if 1 - t0 >= min_fade:  # a fade long enough to read as a dissolve
                el["erode"] = [round(t0, 4), 1, soft]
                tr = el["transparency"][: idx + 1]
                el["transparency"] = tr + [[0.999, round(v0, 3)], [1, 1]]
                eroded += 1
    out["about"] = f"{preset} with the anime pass (kit/vfx/animepass.py: {stepped} mesh layers on twos, {eroded} fades turned into erosion). " + src.get("about", "")
    json.dump(out, open(os.path.join("assets", "effects", f"{new}.json"), "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps({"schema": 1, "status": "pass", "summary": f"animepass {preset} -> {new}: {stepped} mesh layer(s) on {step:g}s, {eroded} fade-out(s) now erode",
                      "next_action": f"lune run kit vfx {new} --game none; python kit/vfx/autorec.py {new} {preset}; compare them side by side"}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
