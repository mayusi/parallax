"""bible.py - a world's BIBLE (LIMITATIONS_FIXES_V3.md stage A.2, the W1 route stage: "World Bible & Walked Greybox ...
SampleTown physical scale (1 stud = 0.28 m), R6 figure in every frame, unobstructed spawn-to-landmark sightlines, and
explicit fixture rules per region card"). <worlds>/bible/<Name>.json says what the world IS before it is dressed:
  { "world": "<Name>", "stud_m": 0.28, "scale": "r6",
    "regions": [ { "name", "area": [x0, z0, x1, z1], "lamps": "avenue" | "lane" | "square" | "none",
                   "fixtures": "<the region's rule in words: what stands where>" } ],
    "landmarks": [ { "name", "pos": [x, y, z] } ] }
Checked: the fields, the blueprint's own rig sheet ("scale": "r6"), every region inside the map, and - on the world
compiled (build/worlds/<Name>.json) - every landmark SEEN from every spawn: the line from the spawn's eye (5 studs up)
to the landmark crosses no solid part (the landmark's own parts, within LANDMARK_OWN studs of it, excepted).
python kit/world/bible.py <Name> [--worlds <dir>] [--build <dir>] [--write]  (--write: a starter bible from the
blueprint when there is none: its spawns' map, one region, its landmark steps) -> one JSON line, as every kit tool."""
import json
import math
import os
import sys

STUD_M = 0.28
LAMP_PLACES = ("avenue", "lane", "square", "none")
LANDMARK_OWN = 8.0  # studs round a landmark whose parts are the landmark itself
EYE = 5.0  # studs over a spawn: an R6 head
AIM = 2.0  # studs over a landmark's given point the line ends (a point on the floor: the floor itself hid it)
PLACEHOLDER = "WRITE"  # (a starter's region text: it does not pass until it is written)


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def problems(bible, blueprint):
    out = []
    if not isinstance(bible, dict):
        return ["the bible is not a JSON object"]
    if bible.get("stud_m") != STUD_M:
        out.append(f'"stud_m" is {STUD_M} (1 stud = 0.28 m: the physical scale the sheet is measured in)')
    if (blueprint or {}).get("scale") != "r6":
        out.append('the blueprint names no rig sheet ("scale": "r6"): every claim of the world is held to it')
    regions = bible.get("regions")
    if not isinstance(regions, list) or not regions:
        out.append('no "regions": every part of the world gets its region card (name, area, lamps, fixtures)')
        regions = []
    for i, r in enumerate(regions):
        if not isinstance(r, dict):
            out.append(f"region {i + 1} is not an object")
            continue
        label = r.get("name") or f"region {i + 1}"
        a = r.get("area")
        if not (isinstance(a, list) and len(a) == 4 and all(isinstance(v, (int, float)) for v in a) and a[0] < a[2] and a[1] < a[3]):
            out.append(f'{label}: "area" is [x0, z0, x1, z1], x0 < x1 and z0 < z1')
        if r.get("lamps") not in LAMP_PLACES:
            out.append(f'{label}: "lamps" is one of {" | ".join(LAMP_PLACES)} (its lamp rule: kit world check\'s lamp_spacing)')
        fx = r.get("fixtures")
        if not isinstance(fx, str) or len(fx.strip()) < 12 or fx.strip().startswith(PLACEHOLDER):
            out.append(f'{label}: "fixtures" says in words what stands where (benches, wells, lamps, signs ...)')
    marks = bible.get("landmarks")
    if not isinstance(marks, list) or not marks:
        out.append('no "landmarks": what a player steers by (seen from every spawn)')
        marks = []
    for i, m in enumerate(marks):
        p = m.get("pos") if isinstance(m, dict) else None
        if not (isinstance(p, list) and len(p) == 3 and all(isinstance(v, (int, float)) for v in p)):
            out.append(f'landmark {i + 1}: "pos" is [x, y, z]')
    return out


def _aabb(p):
    r = p.get("rot") or [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    h = [v / 2 for v in p["size"]]
    ext = [sum(abs(r[a][b]) * h[b] for b in range(3)) for a in range(3)]
    return [p["pos"][a] - ext[a] for a in range(3)], [p["pos"][a] + ext[a] for a in range(3)]


def _hits(a, b, lo, hi):
    """does the segment a -> b pass through the box (slab test)"""
    t0, t1 = 0.0, 1.0
    for k in range(3):
        d = b[k] - a[k]
        if abs(d) < 1e-9:
            if a[k] < lo[k] or a[k] > hi[k]:
                return False
            continue
        u, v = (lo[k] - a[k]) / d, (hi[k] - a[k]) / d
        if u > v:
            u, v = v, u
        t0, t1 = max(t0, u), min(t1, v)
        if t0 > t1:
            return False
    return True


def sightlines(world, marks):
    """[(spawn, landmark name, the part in the way)] for every landmark a spawn does not see"""
    parts = [p for p in world.get("parts") or [] if isinstance(p.get("size"), list) and not p.get("backdrop")]
    spawns = [p["pos"] for p in parts if p.get("spawn") or p.get("name") == "Spawn"]
    solid = [p for p in parts if p.get("collide") is not False and (p.get("transparency") or 0) < 0.5
             and not p.get("spawn") and p.get("name") != "Spawn"]
    boxes = [(_aabb(p), p) for p in solid]
    blocked = []
    for s in spawns:
        eye = [s[0], s[1] + EYE, s[2]]
        for m in marks:
            mp = [m["pos"][0], m["pos"][1] + AIM, m["pos"][2]]
            for (lo, hi), p in boxes:
                c = p["pos"]
                if math.dist(c, m["pos"]) <= LANDMARK_OWN:
                    continue  # (the landmark's own parts)
                if lo[0] <= eye[0] <= hi[0] and lo[1] <= eye[1] <= hi[1] and lo[2] <= eye[2] <= hi[2]:
                    continue  # (the spawn stands in it: a roofed spawn hall is the blueprint's own call)
                if _hits(eye, mp, lo, hi):
                    blocked.append(([round(v) for v in s], m.get("name") or "?", p.get("name") or "Part"))
                    break
    return blocked


def starter(name, blueprint):
    marks = []
    for st in blueprint.get("build") or []:
        for kind, spec in (st or {}).items():
            if isinstance(spec, dict) and spec.get("landmark") is True:
                c = spec.get("center") or spec.get("pos") or [0, 0, 0]
                if len(c) == 2:
                    c = [c[0], 0, c[1]]
                marks.append({"name": spec.get("name") or kind, "pos": c})
    return {"world": name, "stud_m": STUD_M, "scale": "r6",
            "regions": [{"name": "the whole world", "area": [-256, -256, 256, 256], "lamps": "none",
                         "fixtures": PLACEHOLDER + " what stands where in this region (benches, wells, lamps, signs)"}],
            "landmarks": marks}


def main(argv):
    name = argv[0]
    worlds = argv[argv.index("--worlds") + 1] if "--worlds" in argv else "assets/worlds"
    build = argv[argv.index("--build") + 1] if "--build" in argv else "build/worlds"
    bp_path = os.path.join(worlds, f"{name}.json")
    path = os.path.join(worlds, "bible", f"{name}.json")  # (not beside the blueprints: every *.json there is a world)
    if not os.path.isfile(bp_path):
        return {"status": "fail", "summary": f"no blueprint {bp_path}", "next_action": f"lune run kit new world {name}"}
    blueprint = _load(bp_path)
    if not os.path.isfile(path):
        if "--write" in argv:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                json.dump(starter(name, blueprint), f, indent=1)
                f.write("\n")
            return {"status": "fail", "summary": f"a starter bible written: {path}",
                    "next_action": f"fill in its regions' fixture rules and landmarks, then lune run kit world bible {name}"}
        return {"status": "fail", "summary": f"no bible {path}",
                "next_action": f"lune run kit world bible {name} --write (a starter from the blueprint), then fill it in"}
    bible = _load(path)
    found = problems(bible, blueprint)
    world_path = os.path.join(build, f"{name}.json")
    blocked = []
    if not found and os.path.isfile(world_path):
        blocked = sightlines(_load(world_path), bible.get("landmarks") or [])
        for s, m, p in blocked[:3]:
            found.append(f"landmark {m} is not seen from the spawn at {s}: {p} stands in the way")
    elif not found:
        found.append(f"the world is not built ({world_path}): lune run kit world, then this again")
    ok = not found
    return {"status": "pass" if ok else "fail",
            "summary": f"bible {name}: " + ("every region carded, every landmark seen from every spawn" if ok
                                            else f"{len(found)} problem(s): {found[0]}"),
            "next_action": f"lune run kit world greybox {name}" if ok else found[0],
            "problems": found, "blocked": len(blocked)}


if __name__ == "__main__":
    res = main(sys.argv[1:])
    print(json.dumps(res))
    sys.exit(0 if res["status"] == "pass" else 1)
