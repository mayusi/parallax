"""arena_tris.py - the integration arena's SCENE TRIANGLE BUDGET, summed offline (LIMITATIONS_FIXES_V4 §10 / §13.8: the
1.5M triangle ceiling is not readable from Luau - qa.perf cannot count a mesh's triangles - so it is enforced before
export from the build's own numbers):
  - the world: build/worlds/<world>.json's placed parts - a part placing a W3 kit mesh ("mesh": "<name>") counts
    build/worldmeshes/<name>.mesh.json "tris" (the placed-manifest summation); a plain primitive counts its render
    mesh (Block 12, WedgePart 8, CornerWedgePart 6; Cylinder / Ball are engine meshes whose count is not published -
    ESTIMATES, said as such in the output)
  - the hero: build/models/<hero>.manifest.json groups[*].tris (the Blender build's mesh groups, the same model the
    contract hashes)
  - the bodies: R6 characters (the two players + the cutscene's two) at an ESTIMATE per body (5 blocks + the head mesh)
A world part or hero group that names a mesh the build does not have is reported (never counted as 0 in silence).

    python kit/tools/arena_tris.py [--root <dir>] [--world GothicCourtyard] [--hero celestial_sword] [--bodies 4]
                                   [--budget 1500000]
Prints one JSON line {status, summary, next_action, total, budget, parts}; exit 0 under the budget, 1 over or unread.
"""

import argparse
import json
import os
import sys

BUDGET = 1_500_000
PRIMITIVE_TRIS = {"Block": 12, "WedgePart": 8, "CornerWedgePart": 6}
# engine meshes with no published count: generous estimates, flagged
PRIMITIVE_ESTIMATES = {"Cylinder": 128, "Ball": 960}
R6_BODY_ESTIMATE = 5 * 12 + 1000  # five blocks + the R6 head's engine mesh (estimate)


def _read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def world_tris(root, world):
    """-> (tris, estimated_tris, missing meshes, counts by kind) for build/worlds/<world>.json"""
    data = _read(os.path.join(root, "build", "worlds", f"{world}.json"))
    total, estimated, missing, kinds = 0, 0, [], {}
    mesh_cache = {}
    for part in data.get("parts", []):
        mesh = part.get("mesh")
        if mesh:
            if mesh not in mesh_cache:
                p = os.path.join(root, "build", "worldmeshes", f"{mesh}.mesh.json")
                mesh_cache[mesh] = int(_read(p).get("tris", 0)) if os.path.isfile(p) else None
            n = mesh_cache[mesh]
            if n is None:
                missing.append(mesh)
                continue
            total += n
            kinds["mesh:" + mesh] = kinds.get("mesh:" + mesh, 0) + 1
            continue
        shape = part.get("shape") or part.get("class") or "Block"
        if shape in PRIMITIVE_TRIS:
            total += PRIMITIVE_TRIS[shape]
        else:
            n = PRIMITIVE_ESTIMATES.get(shape, PRIMITIVE_ESTIMATES["Ball"])
            total += n
            estimated += n
        kinds[shape] = kinds.get(shape, 0) + 1
    return total, estimated, sorted(set(missing)), kinds


def hero_tris(root, hero):
    """-> (tris, missing groups) for build/models/<hero>.manifest.json"""
    data = _read(os.path.join(root, "build", "models", f"{hero}.manifest.json"))
    total, missing = 0, []
    for name, group in (data.get("groups") or {}).items():
        n = group.get("tris") if isinstance(group, dict) else None
        if isinstance(n, (int, float)):
            total += int(n)
        else:
            missing.append(name)
    return total, missing


def count(root, world="GothicCourtyard", hero="celestial_sword", bodies=4, budget=BUDGET):
    w, w_est, w_missing, kinds = world_tris(root, world)
    h, h_missing = hero_tris(root, hero)
    b = bodies * R6_BODY_ESTIMATE
    total = w + h + b
    estimated = w_est + b
    missing = [f"world mesh {m}" for m in w_missing] + [f"hero group {g}" for g in h_missing]
    ok = total <= budget and not missing
    return {
        "status": "pass" if ok else "fail",
        "summary": f"arena scene {total:,} triangles {'>' if total > budget else '<='} {budget:,}"
        + (f"; unread: {', '.join(missing)}" if missing else "")
        + f" (world {world} {w:,}, hero {hero} {h:,}, {bodies} R6 bodies {b:,}; {estimated:,} of it estimated)",
        "next_action": "none" if ok else (
            "build the missing meshes (kit world / kit asset) and run again" if missing
            else "cut the scene: the hero's game version (kit optimize) or the world's W3 meshes / HLOD"),
        "total": total,
        "budget": budget,
        "estimated": estimated,
        "parts": {"world": w, "hero": h, "bodies": b, "worldKinds": kinds},
    }


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".")
    ap.add_argument("--world", default="GothicCourtyard")
    ap.add_argument("--hero", default="celestial_sword")
    ap.add_argument("--bodies", type=int, default=4)
    ap.add_argument("--budget", type=int, default=BUDGET)
    a = ap.parse_args(argv)
    try:
        out = count(a.root, a.world, a.hero, a.bodies, a.budget)
    except (OSError, ValueError) as e:
        out = {"status": "fail", "summary": f"arena tris: could not read the build ({e})",
               "next_action": "build the world (kit world) and the hero (kit asset) first"}
    print(json.dumps(out))
    return 0 if out["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
