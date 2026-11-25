"""floorplan.py — a building's FLOOR PLANS from the compiled world: one panel per floor, seen from above (walls, stairs,
slabs' stairwells, furniture by name, the reach the play check measured), to LOOK at an interior without Studio.

    python kit/world/floorplan.py <compiled world.json> <Building> [--out build/worlds/floorplans]

Parts belong to the building by their compiled path (<Building>.floorN... / the building step's parts). One JSON line.
"""

import json
import os
import sys

FURNITURE = {"Table": "#8b5a2b", "Bench": "#a0703c", "Hearth": "#6e6e6e", "HearthFire": "#ff8c3c", "Barrel": "#7a4f2a",
             "Cupboard": "#6b4423", "Bed": "#b0413e", "Shelf": "#6b4423", "Desk": "#8b5a2b", "Chest": "#9c6b30",
             "WeaponRack": "#5a5a66", "Crate": "#a67c52", "Wardrobe": "#5e3b1f", "Candelabra": "#c9a227",
             "ArmorStand": "#7d7d8a", "Sack": "#c2a878", "Rug": "#9e3b3b", "Candle": "#ffb050"}


def main(argv):
    if len(argv) < 2:
        print(json.dumps({"status": "fail", "summary": "usage: floorplan.py <world.json> <Building>", "next_action": "pass the compiled world and a building name"}))
        return 2
    world_path, name = argv[0], argv[1]
    out_dir = argv[argv.index("--out") + 1] if "--out" in argv else os.path.join(os.path.dirname(os.path.dirname(world_path)), "worlds", "floorplans")
    w = json.load(open(world_path, encoding="utf-8"))
    bp_spec = None
    mine = [p for p in w["parts"] if str(p.get("path", "")).split(".")[0].endswith(name) or str(p.get("path", "")).find(f"{name}") >= 0]
    if not mine:
        # compiled parts may not carry their path: take everything inside the building's footprint instead
        keep = [p for p in w["parts"] if p.get("name") in ("Slab", "Stair") or p.get("name") in FURNITURE]
        if not keep:
            print(json.dumps({"status": "fail", "summary": f"no parts of {name}", "next_action": "compile the world first"}))
            return 1
    bx = [p for p in w["parts"] if p.get("name") in FURNITURE or p.get("name") in ("Stair",)]
    # the building's floors: the y of its slabs inside the furniture's footprint
    import numpy as np

    xs = [p["pos"][0] for p in bx]
    zs = [p["pos"][2] for p in bx]
    if not xs:
        print(json.dumps({"status": "fail", "summary": f"{name} has no furniture or stairs", "next_action": 'give the building "interior": true and "stairs": true'}))
        return 1
    x0, x1, z0, z1 = min(xs) - 25, max(xs) + 25, min(zs) - 25, max(zs) + 25
    near = [p for p in w["parts"] if x0 <= p["pos"][0] <= x1 and z0 <= p["pos"][2] <= z1]
    slabs = sorted({round(p["pos"][1] + p["size"][1] / 2, 1) for p in near if p.get("name") == "Slab"})
    floors = []
    for y in slabs:
        if not floors or y - floors[-1] > 3:
            floors.append(y)
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    fig, axes = plt.subplots(1, len(floors), figsize=(5 * len(floors), 4.6), dpi=110, squeeze=False)
    counts = []
    for i, y in enumerate(floors):
        ax = axes[0][i]
        top = floors[i + 1] if i + 1 < len(floors) else y + 14
        on = [p for p in near if y - 0.6 <= p["pos"][1] - p["size"][1] / 2 <= top - 0.6 or (p.get("name") == "Slab" and abs(p["pos"][1] + p["size"][1] / 2 - y) < 0.6)]
        n = 0
        for p in on:
            nm = p.get("name")
            sx, sz = p["size"][0], p["size"][2]
            r = p.get("rot")
            if r and abs(r[0][0]) < 0.5:  # (yawed 90: swap the footprint)
                sx, sz = sz, sx
            if nm == "Slab":
                col, z, a = "#d8d0bc", 0, 1
            elif nm == "Stair":
                col, z, a = "#b8956a", 2, 1
            elif nm in FURNITURE:
                col, z, a = FURNITURE[nm], 3, 1
                n += 1
            elif p.get("collide", True):
                col, z, a = "#555555", 1, 1
            else:
                continue
            ax.add_patch(Rectangle((p["pos"][0] - sx / 2, p["pos"][2] - sz / 2), sx, sz, color=col, alpha=a, zorder=z))
            if nm in FURNITURE and nm != "HearthFire":
                ax.text(p["pos"][0], p["pos"][2], nm, fontsize=5, ha="center", va="center", zorder=4)
        counts.append(n)
        ax.set_xlim(x0, x1)
        ax.set_ylim(z1, z0)
        ax.set_aspect("equal")
        ax.set_title(f"floor {i + 1} (y {y:g}): {n} piece(s)", fontsize=8)
        ax.tick_params(labelsize=6)
    os.makedirs(out_dir, exist_ok=True)
    png = os.path.join(out_dir, f"{w.get('name', 'world')}_{name}.png")
    fig.suptitle(f"{name}: floor plans (furniture by rule, kit/lib/interior)", fontsize=9)
    fig.savefig(png, bbox_inches="tight")
    plt.close(fig)
    print(json.dumps({"status": "pass", "summary": f"{name}: {len(floors)} floor(s), furniture per floor {counts}",
                      "next_action": f"LOOK at {png.replace(os.sep, '/')}", "sheet": png.replace(os.sep, "/")}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
