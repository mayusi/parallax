"""kit world web — a world as ONE self-contained web page (three.js + the kit's own shaders).

    python kit/world/web.py build/worlds/<name>.json <out.html>

Reads the flattened world (kit world flatten: parts + terrain field + compiled lighting + terrain colours + water)
and packs it into kit/world/web_template.html: heights as base64 Uint16, parts as base64 Float32 + Uint8 records,
lights / emitters / places of interest as JSON. Nothing is fetched at view time but three.js itself (jsDelivr,
pinned), so the page can be published as an Artifact or opened from disk.

Prints one JSON verdict line (status / summary / next_action / out / bytes).
"""

import base64
import json
import math
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "web_template.html")
LIMIT = 15 * 1024 * 1024  # the Artifact limit is 16 MB; keep a margin

SHAPES = {"Block": 0, "Cylinder": 1, "Ball": 2, "Wedge": 3, "CornerWedge": 4}
# the viewer's material table (index = id); the shader gives each its own procedural surface
MATERIALS = [
    "Plastic", "SmoothPlastic", "Neon", "Wood", "WoodPlanks", "Slate", "Concrete", "Granite", "Brick", "Cobblestone",
    "Rock", "Sandstone", "Basalt", "Limestone", "Pavement", "Marble", "Metal", "DiamondPlate", "CorrodedMetal",
    "Foil", "Glass", "Ice", "Grass", "LeafyGrass", "Sand", "Ground", "Mud", "Snow", "Salt", "Fabric", "Pebble",
    "Asphalt", "CrackedLava", "Glacier", "Plaster", "ForceField",
]
MAT_ID = {m: i for i, m in enumerate(MATERIALS)}
TERRAIN_MATS = ["Grass", "LeafyGrass", "Rock", "Ground", "Mud", "Sand", "Slate", "Snow", "Basalt", "Sandstone",
                "Limestone", "Asphalt", "Concrete", "Pavement", "Glacier", "Ice", "Salt", "Cobblestone", "Brick",
                "CrackedLava", "WoodPlanks"]
# the scanned surface each terrain material borrows its DETAIL from (ambientCG, CC0: VETLOG.md; kit materials --fetch
# <ids> --res 1K). Detail only: each scan is divided by its own mean colour, so the Roblox terrain colour stays the
# colour and the scan gives it real grain. A blueprint overrides with "scans": {"Grass": "Grass001", ...}.
TERRAIN_SCANS = {"Grass": "Grass004", "LeafyGrass": "Grass001", "Rock": "Rock051", "Ground": "Ground108",
                 "Mud": "Ground111", "Snow": "Snow006", "Glacier": "Snow006", "Slate": "Rock035", "Basalt": "Rock035",
                 "Limestone": "Rock051", "Sandstone": "Rock035", "Cobblestone": "Gravel023", "Salt": "Snow006"}
STUD_M = 0.28  # metres per stud (a Roblox character is 5 studs ~ 1.4 m tall at this scale)
SCAN_RES = 1024  # px per scan layer in the page (--scan-res 512 keeps a page under the Artifact limit)


def pack_scans(world, res=1024):
    """the terrain's scanned PBR surfaces (ambientCG, CC0) -> {"alb": [data URI per layer], "nh": [data URI per layer],
    "res", "tile": [layer per TERRAIN_MATS, -1 = none], "studs": [repeat size per TERRAIN_MATS], "mean": [the
    layer's mean colour, sRGB 0..1, per TERRAIN_MATS], "ids"} or None when no scan is on this machine.
    alb = the scan's real colour; nh = its normal (R, G of the GL normal map) + its height (B, the displacement map):
    the viewer lights the surface with the normals and blends materials by height (grass settles between stones)."""
    root = os.environ.get("KIT_MATERIALS") or os.path.join(os.path.expanduser("~"), ".cache", "roblox-kit", "materials")
    pins_p = os.path.join(root, "pins.json")
    if not os.path.isfile(pins_p):
        return None
    try:
        from io import BytesIO
        from PIL import Image, ImageStat
    except ImportError:
        return None
    pins = json.load(open(pins_p, encoding="utf-8"))
    want = dict(TERRAIN_SCANS)
    want.update(world.get("scans") or {})

    def mapname(row, suffix):
        return next((x for x in row.get("maps", []) if x.endswith(suffix)), None)

    ids, tile, studs, mean = [], [-1] * len(TERRAIN_MATS), [8.0] * len(TERRAIN_MATS), [[.5, .5, .5]] * len(TERRAIN_MATS)
    for k, m in enumerate(TERRAIN_MATS):
        sid = want.get(m)
        if sid and f"{sid}@1K" in pins:  # (the 1K fetch: kit materials --fetch <ids> --res 1K)
            sid = f"{sid}@1K"
        row = pins.get(sid) if sid else None
        if not row:
            continue
        color = mapname(row, "_Color.jpg")
        if not color or not os.path.isfile(os.path.join(root, sid, color)):
            continue
        if sid not in ids:
            ids.append(sid)
        tile[k] = ids.index(sid)
        cm = (row.get("tile_cm") or [0])[0] or 300  # (ambientCG lists 0 for some: a 3 m patch)
        studs[k] = round(cm / 100 / STUD_M, 2)
    if not ids:
        return None

    def uri(im, q=84):
        buf = BytesIO()
        im.save(buf, "JPEG", quality=q)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")

    alb, nh, means = [], [], []
    for sid in ids:
        row = pins[sid]
        c = Image.open(os.path.join(root, sid, mapname(row, "_Color.jpg"))).convert("RGB").resize((res, res), Image.LANCZOS)
        means.append([round(v / 255, 4) for v in ImageStat.Stat(c).mean])
        alb.append(uri(c))
        nrm_n = mapname(row, "_NormalGL.jpg")
        hgt_n = mapname(row, "_Displacement.jpg")
        if nrm_n and os.path.isfile(os.path.join(root, sid, nrm_n)):
            nr, ng, _ = Image.open(os.path.join(root, sid, nrm_n)).convert("RGB").resize((res, res), Image.LANCZOS).split()
        else:
            nr = ng = Image.new("L", (res, res), 128)
        if hgt_n and os.path.isfile(os.path.join(root, sid, hgt_n)):
            hb = Image.open(os.path.join(root, sid, hgt_n)).convert("L").resize((res, res), Image.LANCZOS)
        else:
            hb = Image.new("L", (res, res), 128)
        nh.append(uri(Image.merge("RGB", (nr, ng, hb)), 90))
    for k in range(len(TERRAIN_MATS)):
        if tile[k] >= 0:
            mean[k] = means[tile[k]]
    return {"alb": alb, "nh": nh, "res": res, "tile": tile, "studs": studs, "mean": mean, "ids": ids}


# Roblox's default terrain colours (Terrain:GetMaterialColor), used where the blueprint sets none
TERRAIN_DEFAULT = {
    "Grass": [106, 127, 63], "LeafyGrass": [115, 132, 74], "Rock": [102, 108, 111], "Ground": [102, 92, 59],
    "Mud": [58, 46, 36], "Sand": [143, 126, 96], "Slate": [63, 127, 107], "Snow": [195, 199, 218],
    "Basalt": [30, 30, 37], "Sandstone": [137, 90, 71], "Limestone": [206, 173, 148], "Asphalt": [115, 123, 107],
    "Concrete": [127, 102, 63], "Pavement": [148, 148, 140], "Glacier": [101, 176, 234], "Ice": [129, 194, 224],
    "Salt": [198, 189, 181], "Cobblestone": [132, 123, 90], "Brick": [138, 86, 62], "CrackedLava": [232, 156, 74],
    "WoodPlanks": [139, 109, 79],
}


def quat(rot):
    """rows of a Roblox rotation (R00..R22) -> (x, y, z, w)"""
    m00, m01, m02 = rot[0]
    m10, m11, m12 = rot[1]
    m20, m21, m22 = rot[2]
    tr = m00 + m11 + m22
    if tr > 0:
        s = math.sqrt(tr + 1.0) * 2
        return ((m21 - m12) / s, (m02 - m20) / s, (m10 - m01) / s, 0.25 * s)
    if m00 > m11 and m00 > m22:
        s = math.sqrt(1.0 + m00 - m11 - m22) * 2
        return (0.25 * s, (m01 + m10) / s, (m02 + m20) / s, (m21 - m12) / s)
    if m11 > m22:
        s = math.sqrt(1.0 + m11 - m00 - m22) * 2
        return ((m01 + m10) / s, 0.25 * s, (m12 + m21) / s, (m02 - m20) / s)
    s = math.sqrt(1.0 + m22 - m00 - m11) * 2
    return ((m02 + m20) / s, (m12 + m21) / s, 0.25 * s, (m10 - m01) / s)


def b64(raw):
    return base64.b64encode(raw).decode("ascii")


def pack_splat(sp):
    """the painted surface: one byte per cell = its material's index in TERRAIN_MATS (255 = unknown)"""
    if not sp or not sp.get("roles") or not sp.get("palette"):
        return None
    pal = [TERRAIN_MATS.index(m) if m in TERRAIN_MATS else 255 for m in sp["palette"]]
    # (one character a cell: role i is chr(48 + i), kit/world/terrain.py paint_encode)
    raw = bytes(pal[ord(c) - 48] if 0 <= ord(c) - 48 < len(pal) else 255 for c in sp["roles"])
    return {"nx": sp["nx"], "nz": sp["nz"], "x0": sp["x0"], "z0": sp["z0"], "w": sp["w"], "d": sp["d"], "data": b64(raw)}


def pack_meshes(world, mesh_dir, insts):
    """the world meshes the placeholders use: geometry arrays + texture (a data URI, downsized for the page)"""
    out = {}
    rp = os.path.join(mesh_dir, "meshes.json")
    reg = json.load(open(rp, encoding="utf-8")) if os.path.isfile(rp) else {}
    names = sorted({i["mesh"] for i in insts})
    for n in names:
        mj = os.path.join(mesh_dir, n + ".mesh.json")
        if not os.path.isfile(mj):
            continue
        m = json.load(open(mj, encoding="utf-8"))
        tex = None
        png = os.path.join(mesh_dir, n + ".png")
        if os.path.isfile(png):
            try:
                from io import BytesIO
                from PIL import Image
                im = Image.open(png).convert("RGBA").resize((512, 512))
                buf = BytesIO()
                im.save(buf, "PNG", optimize=True)
                tex = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
            except Exception:  # noqa: BLE001
                tex = None
        entry = reg.get(n, {})
        out[n] = {"position": m["position"], "normal": m["normal"], "uv": m["uv"], "min": m["min"], "max": m["max"], "texture": tex,
                  "foliage": bool(entry.get("foliage", entry.get("kind") == "tree")), "uvAtlas": entry.get("kind") == "tree"}
    return out


def pack(world, mesh_dir=None):
    terrain = world.get("terrain") or {}
    grounds = terrain.get("ground") or []
    data = {"name": world.get("name", "World")}
    notes = []

    # ---- ground: the playable heightmap field, then any scenery fields (far mountains: "backdrop")
    def pack_ground(g):
        hs = g["heights"]
        lo, hi = min(hs), max(hs)
        scale = 100.0 if (hi - lo) * 100 < 65535 else 65535 / (hi - lo)
        raw = struct.pack(f"<{len(hs)}H", *[int(round((h - lo) * scale)) for h in hs])
        layers = []
        for l in g.get("layers") or []:
            if l.get("material") in TERRAIN_MATS:
                layers.append({
                    "m": TERRAIN_MATS.index(l["material"]),
                    "h": [l.get("minHeight", -1e5), l.get("maxHeight", 1e5)],
                    "s": [l.get("minSlope", -1), l.get("maxSlope", 91)],
                })
        return {
            "x0": g["x0"], "z0": g["z0"], "step": g["step"], "nx": g["nx"], "nz": g["nz"],
            "lo": lo, "scale": scale, "heights": b64(raw), "cy": g.get("cy", 0),
            "material": TERRAIN_MATS.index(g["material"]) if g.get("material") in TERRAIN_MATS else 0,
            "rock": TERRAIN_MATS.index(g["rock"]) if g.get("rock") in TERRAIN_MATS else 2,
            "rockSlope": g.get("rockSlope") or 90,
            "layers": layers[:8],
            "splat": pack_splat(g.get("splat")),
        }

    if grounds:
        main = next((g for g in grounds if not g.get("backdrop")), grounds[0])
        data["ground"] = pack_ground(main)
        data["groundsExtra"] = [pack_ground(g) for g in grounds if g is not main]
    colors = dict(TERRAIN_DEFAULT)
    for k, v in (world.get("terrainColors") or {}).items():
        colors[k] = v
    data["terrainColors"] = [colors.get(m, [128, 128, 128]) for m in TERRAIN_MATS]
    data["terrainNames"] = TERRAIN_MATS
    data["scans"] = pack_scans(world, SCAN_RES) if grounds else None
    if grounds and not data["scans"]:
        notes.append("no terrain scans on this machine (kit materials --fetch Grass004 Rock051 ... --res 1K): procedural ground only")
    data["water"] = [{"center": w["center"], "size": w["size"]} for w in terrain.get("water") or []]
    data["waterLook"] = world.get("water") or {}
    data["lighting"] = world.get("lighting") or {}
    data["ambient"] = world.get("ambient") or ""

    # ---- parts: Float32 x10 (pos, size, quat) + Uint8 x8 (shape, material, r, g, b, alpha, flags, 0)
    floats, bytes_ = [], bytearray()
    lights, emitters, places = [], [], []
    mesh_insts = []
    skipped = 0
    solids = terrain.get("solids") or []
    parts = list(world.get("parts") or [])
    for s in solids:  # terrain balls / blocks: drawn as parts in the terrain's material
        spec = s.get("spec") or {}
        if s.get("kind") == "ball" and spec.get("center") and spec.get("radius"):
            r = spec["radius"] * 2
            mat = spec.get("material", "Rock")
            parts.append({"name": "TerrainBall", "pos": spec["center"], "size": [r, r, r], "shape": "Ball",
                          "rot": [[1, 0, 0], [0, 1, 0], [0, 0, 1]], "material": mat, "terrain": True,
                          "color": colors.get(mat, [120, 120, 120]), "collide": True})
        elif s.get("kind") == "block" and spec.get("center") and spec.get("size"):
            mat = spec.get("material", "Rock")
            parts.append({"name": "TerrainBlock", "pos": spec["center"], "size": spec["size"], "shape": "Block",
                          "rot": [[1, 0, 0], [0, 1, 0], [0, 0, 1]], "material": mat, "terrain": True,
                          "color": colors.get(mat, [120, 120, 120]), "collide": True})
    count = 0
    for p in parts:
        name = p.get("name") or ""
        if name.startswith("Grace_"):
            places.append({"name": name[6:], "kind": "grace", "pos": p["pos"]})
        for c in p.get("children") or []:
            if c.get("kind") == "light":
                sp = c.get("spec") or {}
                lights.append({"pos": p["pos"], "color": sp.get("color", [255, 255, 255]),
                               "range": sp.get("range", 16), "brightness": sp.get("brightness", 1)})
            elif c.get("kind") == "particles":
                emitters.append({"pos": p["pos"], "size": p["size"], "preset": c.get("preset"),
                                 "backdrop": bool(p.get("backdrop"))})
        if p.get("mesh"):  # a world mesh placeholder: drawn as its mesh, not as a part
            mesh_insts.append({"mesh": p["mesh"], "pos": p["pos"], "size": p["size"], "rot": p.get("rot"),
                               "col": bool(p.get("meshCollide")),
                               "color": p.get("color") or [128, 128, 128], "material": p.get("material") or "Plastic"})
            continue
        t = p.get("transparency") or 0
        if t >= 0.98:
            skipped += 1
            continue
        cls = p.get("class") or "Part"
        shape = "Wedge" if cls == "WedgePart" else "CornerWedge" if cls == "CornerWedgePart" else p.get("shape") or "Block"
        q = quat(p.get("rot") or [[1, 0, 0], [0, 1, 0], [0, 0, 1]])
        floats.extend([*p["pos"], *p["size"], *q])
        col = p.get("color") or [163, 162, 165]
        flags = (1 if p.get("backdrop") else 0) | (2 if p.get("collide", True) else 0) \
            | (4 if p.get("spawn") or cls == "SpawnLocation" else 0) | (8 if p.get("terrain") else 0)
        bytes_ += bytes([SHAPES.get(shape, 0), MAT_ID.get(p.get("material") or "Plastic", 0),
                         *[max(0, min(255, int(v))) for v in col[:3]], int(round(t * 255)), flags, 0])
        if flags & 4:
            places.append({"name": "Spawn", "kind": "spawn", "pos": p["pos"]})
        count += 1
    data["parts"] = {"count": count, "f": b64(struct.pack(f"<{len(floats)}f", *floats)), "u": b64(bytes(bytes_))}
    data["materials"] = MATERIALS
    meshes = pack_meshes(world, mesh_dir, mesh_insts) if mesh_dir and mesh_insts else {}
    names = sorted(meshes)
    inst = []
    for i in mesh_insts:
        if i["mesh"] in meshes:
            q = quat(i.get("rot") or [[1, 0, 0], [0, 1, 0], [0, 0, 1]])
            inst.append({"m": names.index(i["mesh"]), "f": [*i["pos"], *i["size"], *q], "c": i["color"],
                         "mat": MAT_ID.get(i["material"], 0), **({"col": 1} if i.get("col") else {})})
    data["meshes"] = {"names": names, "data": [meshes[n] for n in names], "inst": inst}
    if mesh_insts and not meshes:
        notes.append(f"{len(mesh_insts)} mesh placeholder(s) but no meshes in {mesh_dir} (kit world meshes)")
    data["lights"] = lights
    data["emitters"] = emitters
    for o in world.get("objectives") or []:
        places.append({"name": o.get("name", "objective"), "kind": "objective", "pos": o["pos"]})
    data["places"] = places
    # worn trails (path "worn"): strokes the viewer rasterises into a paint mask over the terrain
    data["paints"] = [{"m": TERRAIN_MATS.index(st["material"]) if st.get("material") in TERRAIN_MATS else 3,
                       "w": st.get("width", 8), "p": [[round(q[0], 1), round(q[2], 1)] for q in st.get("points", [])]}
                      for st in (world.get("paints") or [])]
    return data, count, skipped, len(lights), len(emitters), notes


def main(argv):
    if len(argv) < 3:
        print(json.dumps({"status": "fail", "summary": "usage: web.py <flat world.json> <out.html>",
                          "next_action": "lune run kit world web <Name>"}))
        return 2
    src, out = argv[1], argv[2]
    global SCAN_RES
    if "--scan-res" in argv:
        SCAN_RES = int(argv[argv.index("--scan-res") + 1])
    world = json.load(open(src, encoding="utf-8"))
    mesh_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(src))), "worldmeshes")
    data, count, skipped, nl, ne, notes = pack(world, mesh_dir)
    with open(TEMPLATE, encoding="utf-8") as f:
        tpl = f.read()
    if "/*__WORLD__*/" not in tpl:
        print(json.dumps({"status": "fail", "summary": "web_template.html lost its /*__WORLD__*/ slot",
                          "next_action": "restore the slot in kit/world/web_template.html"}))
        return 1
    page = tpl.replace("__TITLE__", f"{data['name']} Atlas").replace(
        "/*__WORLD__*/null", json.dumps(data, separators=(",", ":")))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    # <name>.html opens from disk (a whole document); <name>.artifact.html is the body an Artifact publish wraps itself
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
                '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
                '<style>html,body{margin:0}</style>\n</head>\n<body>\n' + page + '\n</body>\n</html>\n')
    with open(os.path.splitext(out)[0] + ".artifact.html", "w", encoding="utf-8", newline="\n") as f:
        f.write(page)
    size = os.path.getsize(out)
    ok = "ground" in data
    if size > LIMIT:
        notes.append(f"{size / 1048576:.1f} MB is over the Artifact limit: publish with --scan-res 512")
    summary = (f"{data['name']}: {count} part(s) ({skipped} invisible skipped), {nl} light(s), {ne} emitter(s), "
               f"{len(data['places'])} place(s), {size / 1048576:.1f} MB -> {out}")
    if notes:
        summary += " (" + "; ".join(notes) + ")"
    nxt = (f"open {out} in a browser (or publish it as an Artifact)" if ok else
           "the world has no heightmap ground: add a heightmap terrain op")
    print(json.dumps({"status": "pass" if ok else "fail", "summary": summary, "next_action": nxt,
                      "out": out, "bytes": size}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
