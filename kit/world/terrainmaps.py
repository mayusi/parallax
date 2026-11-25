"""terrainmaps.py — the scanned surfaces (ambientCG 1K, CC0: VETLOG.md) as Roblox MaterialVariant maps.

    python kit/world/terrainmaps.py <out_dir> [--materials Grass,Rock,...]
    (normally: lune run kit world materials)

For each terrain material that has a scan (kit/world/web.py TERRAIN_SCANS; a blueprint's "scans" overrides), writes
<scan>__color.png, <scan>__normal.png (the OpenGL normal map: Roblox's convention), <scan>__roughness.png at 1024 px
(Roblox's largest) into <out_dir>, and <out_dir>/terrainmaps.json:
  { "<Material>": { "scan": "<id>", "studs": <tile size in studs>, "color": "<file>", "normal": ..., "roughness": ... } }
`kit upload` sends the PNGs (ids.terrainmaps); `kit world` then writes a MaterialVariant per material into
MaterialService (src/materials) and the runtime overrides the base material with it
(MaterialService:SetBaseMaterialOverride). A material whose scan has no normal / roughness map is skipped (named).
Prints one JSON verdict line.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

STUD_M = 0.28
MIN_STUDS = 8.0  # (a 1.4 m grass scan at true scale repeats every 5 studs: visible from a player's eye)


def main(argv):
    if not argv:
        print(json.dumps({"status": "fail", "summary": "usage: terrainmaps.py <out_dir> [--materials A,B]",
                          "next_action": "lune run kit world materials"}))
        return 2
    out = os.path.abspath(argv[0])
    only = None
    if "--materials" in argv:
        only = set(argv[argv.index("--materials") + 1].split(","))
    import web  # TERRAIN_SCANS, TERRAIN_MATS
    from PIL import Image

    root = os.environ.get("KIT_MATERIALS") or os.path.join(os.path.expanduser("~"), ".cache", "roblox-kit", "materials")
    pins_p = os.path.join(root, "pins.json")
    if not os.path.isfile(pins_p):
        print(json.dumps({"status": "fail", "summary": "no scans on this machine",
                          "next_action": "lune run kit materials --fetch Grass004 Rock051 ... --res 1K (the owner's OK first)"}))
        return 1
    pins = json.load(open(pins_p, encoding="utf-8"))
    os.makedirs(out, exist_ok=True)
    reg, made, skipped = {}, set(), []
    for mat, sid in web.TERRAIN_SCANS.items():
        if only and mat not in only:
            continue
        key = f"{sid}@1K" if f"{sid}@1K" in pins else sid
        row = pins.get(key)
        if not row:
            skipped.append(f"{mat} ({sid}: not fetched)")
            continue
        maps = {}
        for kind, suffix in (("color", "_Color.jpg"), ("normal", "_NormalGL.jpg"), ("roughness", "_Roughness.jpg")):
            name = next((x for x in row.get("maps", []) if x.endswith(suffix)), None)
            if name and os.path.isfile(os.path.join(root, key, name)):
                maps[kind] = os.path.join(root, key, name)
        if len(maps) < 3:
            skipped.append(f"{mat} ({sid}: missing {', '.join(k for k in ('color', 'normal', 'roughness') if k not in maps)})")
            continue
        files = {}
        for kind, src in maps.items():
            fname = f"{sid}__{kind}.png"
            files[kind] = fname
            if sid + kind not in made:
                im = Image.open(src)
                im = im.convert("L" if kind == "roughness" else "RGB")
                if max(im.size) > 1024:
                    im = im.resize((1024, 1024), Image.LANCZOS)
                im.save(os.path.join(out, fname), optimize=True)
                made.add(sid + kind)
        cm = (row.get("tile_cm") or [0])[0] or 300
        reg[mat] = {"scan": sid, "studs": round(max(MIN_STUDS, cm / 100 / STUD_M), 2), **files}
    with open(os.path.join(out, "terrainmaps.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(reg, fh, indent=1)
    ok = bool(reg)
    print(json.dumps({"status": "pass" if ok else "fail",
                      "summary": f"terrain maps: {len(reg)} material(s) from {len(made) // 3} scan(s) -> {out.replace(os.sep, '/')}"
                                 + (f"; skipped {', '.join(skipped)}" if skipped else ""),
                      "next_action": "lune run kit upload (the maps), then lune run kit world (MaterialVariants in MaterialService)"
                      if ok else "fetch scans first: lune run kit materials --fetch <ids> --res 1K",
                      "materials": sorted(reg)}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
