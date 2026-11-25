"""surfaces.py — the SurfaceAppearance TEMPLATES a live game needs (mission 02-vfx 5.9, the engine facts):

    lune run kit vfx surfaces        (also a step of `lune run kit vfx`)

A runtime mesh gets texture alpha + glow only through a SurfaceAppearance (ColorMap + EmissiveMask + AlphaMode
Transparency) - and a game script may NOT set its maps (Plugin capability, measured 2026-10-16). Rojo can: it writes
ColorMapContent / EmissiveMaskContent into the place (Rojo 7.7, checked by building one). So every texture a preset's
mesh layer draws with `surface` gets one template, named by the texture key, in assets/effects/_surfaces.model.json
(-> ReplicatedStorage.VfxPresets._surfaces in every game: the folder is already mapped; the "_" keeps it out of every
preset scan): VfxStage clones it onto the EditableMesh part (Studio, with plugin rights, builds one on the spot instead). A texture without an uploaded id cannot have one: named, not written.
Prints one JSON line {schema, status, summary, next_action, ...}.
"""

import glob
import json
import os
import sys

EFFECTS = os.path.join("assets", "effects")
OUT = os.path.join(EFFECTS, "_surfaces.model.json")  # every game maps assets/effects -> ReplicatedStorage.VfxPresets


def main(argv):
    reg = json.load(open(os.path.join(EFFECTS, "_textures.json"), encoding="utf-8"))
    used = {}
    for p in sorted(glob.glob(os.path.join(EFFECTS, "*.json"))):
        if os.path.basename(p).startswith("_"):
            continue
        try:
            d = json.load(open(p, encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        for el in d.get("layers", []) if isinstance(d, dict) else []:
            # a mesh layer with `surface`, every mesh trail (the ribbon draws its texture through one, always), and a
            # decal with `wrap` (the mark is a mesh sheet: with no template a live game draws it as an opaque square)
            meshy = ((el.get("kind") == "mesh" and el.get("surface") is not None) or (el.get("kind") == "trail" and el.get("mesh") is True)
                     or (el.get("kind") == "decal" and el.get("wrap") not in (None, False))) if isinstance(el, dict) else False
            if meshy and isinstance(el.get("texture"), str):
                used.setdefault(el["texture"], set()).add(os.path.basename(p)[:-5])
    children, missing, unglowed = [], [], []
    for key in sorted(used):
        e = reg.get(key) if isinstance(reg.get(key), dict) else {}
        tid = e.get("id") or ""
        if not tid:
            missing.append(key)
            continue
        # its own glow mask (fxfinish post.emissive: <key>_glow) when it has one and it is uploaded; else the sheet
        # itself, as before (every lit pixel glows alike) - and said
        gkey = e.get("emissive")
        g = reg.get(gkey) if isinstance(gkey, str) and isinstance(reg.get(gkey), dict) else {}
        gid = g.get("id") or ""
        if gkey and not gid:
            unglowed.append(key)
        children.append({"name": key, "className": "SurfaceAppearance", "properties": {
            "AlphaMode": "Transparency", "ColorMap": tid, "EmissiveMaskContent": gid or tid, "EmissiveStrength": 5}})
    model = {"className": "Folder", "children": children}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    text = json.dumps(model, indent=2) + "\n"
    old = open(OUT, encoding="utf-8").read() if os.path.isfile(OUT) else None
    if old != text:
        open(OUT, "w", encoding="utf-8", newline="\n").write(text)
    users = ", ".join(f"{k} ({', '.join(sorted(v))})" for k, v in sorted(used.items()))
    status = "warn" if missing or unglowed else "pass"
    print(json.dumps({"schema": 1, "status": status,
                      "summary": f"vfx surfaces: {len(children)} SurfaceAppearance template(s) -> {OUT.replace(os.sep, '/')}"
                                 + (f" for {users}" if users else "") + (f"; NOT uploaded (no template): {', '.join(missing)}" if missing else "")
                                 + (f"; glow mask NOT uploaded (the sheet itself glows): {', '.join(unglowed)}" if unglowed else ""),
                      "next_action": ("upload first: lune run kit upload --only build/textures/<key>.png" if missing
                                      else "rojo build / kit verify puts them in ReplicatedStorage.VfxPresets._surfaces"),
                      "templates": [c["name"] for c in children], "missing": missing, "unglowed": unglowed}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
