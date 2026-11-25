"""meshify.py — turn a preset's flipbook CARDS (one camera-facing sprite playing a drawn flipbook: an aura, a glow, a
burst drawing) into MESH cards: `cards` meshes (crossed vertical planes through the effect's axis) that play the same
flipbook on their UVs — the drawing keeps its look and gains depth (it no longer turns to face the camera).

    python kit/vfx/meshify.py <preset> [--as <new name>] [--planes 3] [--only <regex>]

Converts a sprite layer when it is ONE particle (count 1, no rate), camera-facing (FacingCamera / FacingCameraWorldUp),
emissive (lightEmission >= 0.5, drawn as Neon) and plays a flipbook (Loop / OneShot). Everything else is copied as
it is and listed under "kept" (rate emitters, dust, velocity-aligned streaks): say why in the next action.
Writes assets/effects/<new>.json (default <preset>_meshaura); the original is never touched (the owner's rule: never
overwrite a loved version). Proven on saiyan_ssj_3d -> saiyan_ssj_3d_meshaura (owner: "NOT THAT BAD").
Prints one JSON line.
"""

import copy
import json
import os
import re
import sys

FACING = ("FacingCamera", "FacingCameraWorldUp")


def convertible(el):
    if el.get("kind") != "sprite":
        return False, None
    if el.get("count") != 1 or el.get("rate"):
        return False, "an emitter (rate / count > 1), not one card"
    if (el.get("orientation") or "FacingCamera") not in FACING:
        return False, f"orientation {el.get('orientation')} (not camera-facing)"
    if (el.get("lightEmission") if el.get("lightEmission") is not None else 0) < 0.5:
        return False, "not emissive (a lit card: dust / smoke)"
    fb = el.get("flipbook")
    if not fb or (fb.get("mode") or "Loop") not in ("Loop", "OneShot"):
        return False, "no Loop / OneShot flipbook"
    return True, None


def scale_of(size):
    if isinstance(size, (int, float)):
        return [size, size, size]
    if isinstance(size, list) and size and isinstance(size[0], list):  # a size sequence [[t, s], ...]
        return [[k[0], [k[1], k[1], k[1]]] for k in size]
    return [1, 1, 1]


def meshify(el, planes):
    life = el["lifetime"][0] if isinstance(el.get("lifetime"), list) else el.get("lifetime", el.get("life", 1))
    m = {"name": el["name"] + "_mesh", "kind": "mesh", "at": el.get("at", 0), "life": life, "point": el.get("point", [0, 0, 0]),
         "shape": "cards", "params": {"count": planes, "width": 1, "height": 1}, "texture": el["texture"], "material": "Neon",
         "scale": scale_of(el.get("size", 1)),
         "flipbook": {k: v for k, v in el["flipbook"].items() if k in ("layout", "fps", "mode", "startRandom")}}
    for k in ("color", "transparency"):
        if k in el:
            m[k] = el[k]
    rot = el.get("rotation")
    if rot and (rot[0] if isinstance(rot, list) else rot):  # a turned card: turn the planes over
        m["rotate"] = [0, 0, rot[0] if isinstance(rot, list) else rot]
    return m


def main(argv):
    if not argv:
        print(json.dumps({"schema": 1, "status": "fail", "summary": "meshify: needs a preset", "next_action": "python kit/vfx/meshify.py <preset> [--as <new>]"}))
        return 2
    preset, opts, i = argv[0], {}, 1
    while i < len(argv) - 1:
        opts[argv[i]] = argv[i + 1]
        i += 2
    src_path = os.path.join("assets", "effects", f"{preset}.json")
    if not os.path.isfile(src_path):
        print(json.dumps({"schema": 1, "status": "fail", "summary": f"meshify: no preset {src_path}", "next_action": "check the name"}))
        return 1
    new = opts.get("--as", f"{preset}_meshaura")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", new) or new == preset:
        print(json.dumps({"schema": 1, "status": "fail", "summary": f"meshify: bad new name {new!r} (and never the original's)", "next_action": "--as <new_name>"}))
        return 2
    planes = int(opts.get("--planes", 3))
    only = re.compile(opts["--only"]) if "--only" in opts else None
    src = json.load(open(src_path, encoding="utf-8"))
    out = copy.deepcopy(src)
    layers, done, kept = [], [], []
    for el in src.get("layers", []):
        ok, why = convertible(el)
        if ok and (only is None or only.search(el["name"])):
            layers.append(meshify(el, planes))
            done.append(el["name"])
        else:
            layers.append(el)
            if why:
                kept.append(f"{el['name']}: {why}")
    out["layers"] = layers
    out["about"] = f"{preset} with its flipbook cards made MESH (kit/vfx/meshify.py: {len(done)} card(s) -> crossed `cards` meshes playing the same flipbook). " + src.get("about", "")
    json.dump(out, open(os.path.join("assets", "effects", f"{new}.json"), "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps({"schema": 1, "status": "pass" if done else "warn", "summary": f"meshify {preset} -> {new}: {len(done)} card(s) now mesh ({', '.join(done) or 'none'}); {len(kept)} sprite layer(s) kept as they are",
                      "next_action": f"lune run kit vfx {new} --game none, record it, then compare it with {preset} (same views, same moments)", "kept": kept}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
