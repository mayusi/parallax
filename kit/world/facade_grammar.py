"""facade_grammar.py - W3, HOUSES PUT TOGETHER FROM THE MODULAR KIT BY RULES (LIMITATIONS_FIXES_V4 5.1 / 5.4 step 2 /
13.5: "facade_grammar.py (WFC)"; kit/world/modkit.py's eighteen pieces on two shared trim sheets).

A facade is split (Mueller et al. 2006: facade -> storeys -> bays) into GRID-stud bays, its width shared out evenly
(22 studs: five bays of 4.4); each bay of each storey is filled by ONE bay module chosen under adjacency rules - the
small, deterministic constraint solve WFC is used for (mxgmn's WaveFunctionCollapse, the rules only, no sample code):
  * the doorway (portal_8, two bays) stands on the ground storey at the door bay, nowhere else;
  * windows keep COLUMNS: a bay that is a window on one storey is a window on every storey (a twin lancet over the
    doorway, the axis of the front); the corner bays stay wall (the quoins wrap them);
  * no two single windows side by side: a wall bay between (rhythm), each window column picked from the seed among
    the ones the rules leave;
  * neighbouring wall bays of a storey merge into wall_8 (fewer pieces, one seam);
  * a plinth under every bay but the doorway, a string course on every storey line, a cornice on top, crenellated
    parapets on a flat roof; a quoin up the left corner of every facade, storey by storey (four facades: four
    corners); buttresses only where both bays beside the line are wall; slate slopes on the eave sides, gable ends on
    the others, a ridge, a chimney on the ridge and a dormer over a window column (from the seed).
A module may be stretched along the facade or the roof's slope to fit (a placement's "scale"); check() refuses one
stretched past the trims' density bar (35..70 px/stud, modkit.DENSITY) and any rule broken: every bay of every
storey covered once, columns aligned, the doorway on the ground and wide / high enough for the R6 rig.
house(width, depth, storeys, door_side, seed, roof) -> placements in the house's own frame (its middle at the
origin, y up from its ground floor): [{ module, facade, pos, yaw, scale }]. Pure; the gothic court's nine houses are
put together in kit/test/python/test_world_facade_grammar.py and looked at in Blender (kit/world/modkit_blender.py)."""
import math
import random

import modkit as M

GRID, FLOOR = M.GRID, M.FLOOR
STRETCH = (0.85, 1.25)  # how far a bay module may be stretched along its facade


def bays_of(width):
    """(how many bays, each bay's width) for a facade `width` studs long"""
    n = max(1, int(math.floor(width / GRID + 1e-9)))  # (stretched, never squeezed: a squeezed trim reads finer than the bar)
    return n, width / n


def columns(n, door, seed):
    """each bay's column: "door" (two bays from `door`), "window" or "wall". Corners wall; no two windows side by
    side; the window columns from the seed among the ones the rules leave (densest rhythm first)"""
    col = ["wall"] * n
    if door is not None:
        col[door] = col[door + 1] = "door"
    rng = random.Random(seed)
    free = [i for i in range(1, n - 1) if col[i] == "wall"]
    # the bays that may hold a window: not a corner, not the door, not beside the door's frame
    cand = [i for i in free if not (door is not None and i in (door - 1, door + 2) and n < 6)]
    rng.shuffle(cand)
    cand.sort(key=lambda i: (i % 2 != (1 if door is None else (door + 1) % 2), rng.random()))
    for i in cand:
        if (i - 1 < 0 or col[i - 1] != "window") and (i + 1 >= n or col[i + 1] != "window"):
            col[i] = "window"
    return col


def facade(width, storeys, door=None, seed=1, roof="gable", eave=True, chimney=False, dormer=False):
    """one facade's placements in its own frame (x along it from its left end, y up, z out to the street)"""
    n, bw = bays_of(width)
    sx = bw / GRID
    col = columns(n, door, seed)
    out = []

    def put(module, x, y, z=0.0, scale=(1.0, 1.0, 1.0), role=None):
        out.append({"module": module, "pos": [round(x, 4), round(y, 4), round(z, 4)], "yaw": 0,
                    "scale": [round(s, 4) for s in scale], "role": role})

    for s in range(storeys):
        y = s * FLOOR
        i = 0
        while i < n:
            c = col[i]
            if c == "door":
                put("portal_8" if s == 0 else "twin_lancet_8", i * bw, y, scale=(sx, 1, 1), role=("door" if s == 0 else "window", i, s))
                i += 2
            elif c == "window":
                put("lancet_4", i * bw, y, scale=(sx, 1, 1), role=("window", i, s))
                i += 1
            elif i + 1 < n and col[i + 1] == "wall":
                put("wall_8", i * bw, y, scale=(sx, 1, 1), role=("wall", i, s))
                i += 2
            else:
                put("wall_4", i * bw, y, scale=(sx, 1, 1), role=("wall", i, s))
                i += 1
        if s > 0:
            for i in range(n):
                put("string_4", i * bw, y - 0.4, scale=(sx, 1, 1), role=("band", i, s))
        put("quoin", 0.0, y, role=("corner", 0, s))
    for i in range(n):
        if col[i] != "door":
            put("plinth_4", i * bw, 0.0, scale=(sx, 1, 1), role=("plinth", i, 0))
    top = storeys * FLOOR
    for i in range(n):
        put("cornice_4", i * bw, top - 1.6, scale=(sx, 1, 1), role=("cornice", i, storeys))
        if roof == "flat":
            put("parapet_4", i * bw, top, scale=(sx, 1, 1), role=("parapet", i, storeys))
    # buttresses on the lines between two wall bays (never in front of a window or the doorway)
    for i in range(1, n):
        if col[i - 1] == "wall" and col[i] == "wall" and n >= 5 and i % 2 == 0:
            for s in range(storeys):
                put("buttress", i * bw - 1.0, s * FLOOR, role=("buttress", i, s))
    if dormer and roof == "gable" and eave:
        wins = [i for i in range(n) if col[i] == "window"]
        if wins:
            i = wins[random.Random(seed + 3).randrange(len(wins))]
            put("dormer", i * bw + bw / 2 - 2.3, top + 1.0, -2.0, role=("dormer", i, storeys))
    return out, col, n, bw


def _xf(lx, lz, side, w, d):
    """a facade's local (x, z) -> the house's (x, z), and its yaw (degrees, about +y)"""
    if side == "S":
        return -w / 2 + lx, d / 2 + lz, 0
    if side == "E":
        return w / 2 + lz, d / 2 - lx, 90
    if side == "N":
        return w / 2 - lx, -d / 2 - lz, 180
    return -w / 2 - lz, -d / 2 + lx, 270


def house(width, depth, storeys, door_side="S", seed=1, roof="gable"):
    """-> (placements, facades): the four facades round a width x depth footprint (x across, z deep) and the roof"""
    sides = {"S": width, "E": depth, "N": width, "W": depth}
    ridge_x = width >= depth  # (the ridge runs along the longer side: the eaves are the long facades)
    placements, facades = [], {}
    for k, side in enumerate(("S", "E", "N", "W")):
        length = sides[side]
        n, _ = bays_of(length)
        door = None
        if side == door_side and n >= 3:
            door = (n - 2) // 2
        eave = (side in ("S", "N")) == ridge_x
        out, col, n, bw = facade(length, storeys, door, seed * 31 + k, roof, eave, dormer=(side == door_side))
        facades[side] = {"length": length, "bays": n, "bay": bw, "columns": col, "door": door, "eave": eave}
        for p in out:
            x, z, yaw = _xf(p["pos"][0], p["pos"][2], side, width, depth)
            q = dict(p)
            q["facade"] = side
            q["pos"] = [round(x, 4), p["pos"][1], round(z, 4)]
            q["yaw"] = yaw
            placements.append(q)
    if roof == "gable":
        top = storeys * FLOOR
        span = depth if ridge_x else width  # (across the ridge)
        length = width if ridge_x else depth
        run = span / 2  # (roof_4 is made for a 10-stud run at 45 degrees: scaled to this one)
        n, bw = bays_of(length)
        for side in (("S", "N") if ridge_x else ("E", "W")):
            for i in range(n):
                x, z, yaw = _xf(i * bw, 0.0, side, width, depth)
                placements.append({"module": "roof_4", "facade": side, "pos": [round(x, 4), top, round(z, 4)], "yaw": yaw,
                                   "scale": [round(bw / GRID, 4), round(run / 10.0, 4), round(run / 10.0, 4)],
                                   "role": ("roof", i, storeys)})
        for i in range(n):
            # the ridge over the middle, along the long axis
            if ridge_x:
                x, z, yaw = -width / 2 + i * bw, 0.0, 0
            else:
                x, z, yaw = 0.0, depth / 2 - i * bw, 90
            placements.append({"module": "ridge_4", "facade": "ridge", "pos": [round(x, 4), top + run, round(z, 4)],
                               "yaw": yaw, "scale": [round(bw / GRID, 4), 1, 1], "role": ("ridge", i, storeys)})
        for side in (("E", "W") if ridge_x else ("S", "N")):
            x, z, yaw = _xf(0.0, 0.0, side, width, depth)
            placements.append({"module": "gable_16", "facade": side, "pos": [round(x, 4), top, round(z, 4)], "yaw": yaw,
                               "scale": [round(span / 16.0, 4), round(run / 8.0, 4), 1], "role": ("gable", 0, storeys)})
        cx, cz = (width / 2 - 4.0, 0.0) if ridge_x else (0.0, depth / 2 - 4.0)
        placements.append({"module": "chimney", "facade": "ridge", "pos": [round(cx, 4), top + run - 2.0, round(cz, 4)],
                           "yaw": 0, "scale": [1, 1, 1], "role": ("chimney", 0, storeys)})
    return placements, facades


def check(placements, facades, storeys, kit=None):
    """the grammar's rules on a house -> errors"""
    kit = kit or M.build_kit()
    errors = []
    lo, hi = M.DENSITY
    # every module's own density range (measured once): stretched by a scale it must stay in the bar
    dens = {}
    for name, m in kit.items():
        ds = []
        for part in m["parts"]:
            mesh = M.Mesh()
            mesh.v, mesh.f, mesh.uv = part["verts"], part["faces"], part["uvs"]
            ds += [d for a, d in mesh.tri_area_density() if a >= 0.02]
        dens[name] = (min(ds), max(ds))
    for p in placements:
        if p["module"] not in kit:
            errors.append(f"no module {p['module']}")
            continue
        s = p["scale"]
        dlo, dhi = dens[p["module"]]
        if dlo / max(s) < lo - 1e-6 or dhi / min(s) > hi + 1e-6:
            errors.append(f"{p['module']} on {p['facade']} stretched {s}: its trims fall to {dlo / max(s):.0f}..{dhi / min(s):.0f} px/stud (the bar {lo:.0f}..{hi:.0f})")
        if kit[p["module"]]["kind"] == "bay" and not (STRETCH[0] - 1e-6 <= s[0] <= STRETCH[1] + 1e-6):
            errors.append(f"{p['module']} on {p['facade']} stretched {s[0]:.2f} along the facade (the grammar's {STRETCH})")
    for side, f in facades.items():
        n = f["bays"]
        cover = [[0] * n for _ in range(storeys)]
        win = [[False] * n for _ in range(storeys)]
        for p in placements:
            if p["facade"] != side or kit[p["module"]]["kind"] != "bay":
                continue
            kind, i, s = p["role"]
            span = kit[p["module"]]["grid"]
            for j in range(i, i + span):
                if j >= n:
                    errors.append(f"{side}: {p['module']} runs past the facade's last bay")
                    continue
                cover[s][j] += 1
                win[s][j] = kind in ("window", "door")
            if p["module"] == "portal_8" and s != 0:
                errors.append(f"{side}: a doorway on storey {s + 1}")
        for s in range(storeys):
            for j in range(n):
                if cover[s][j] != 1:
                    errors.append(f"{side}: storey {s + 1} bay {j + 1} covered {cover[s][j]} times")
        for j in range(n):
            if len({win[s][j] for s in range(storeys)}) > 1:
                errors.append(f"{side}: bay {j + 1}'s window does not keep its column")
        for s in range(storeys):
            for j in range(n - 1):
                both = [p for p in placements if p["facade"] == side and p["module"] == "lancet_4" and p["role"][2] == s and p["role"][1] in (j, j + 1)]
                if len(both) == 2:
                    errors.append(f"{side}: two single windows side by side (storey {s + 1}, bays {j + 1}-{j + 2})")
        if f["door"] is not None:
            portal = kit["portal_8"]["opening"]
            sx = f["bay"] / GRID
            if portal["width"] * sx < M.DOOR_MIN[0] or portal["apex"] < M.DOOR_MIN[1]:
                errors.append(f"{side}: the doorway {portal['width'] * sx:.1f} x {portal['apex']:.1f} (the rig needs {M.DOOR_MIN})")
    return errors
