"""WHICH COLLISION SHAPE AND WHICH LEVEL OF DETAIL a mesh gets in the game (the owner's method lists, 2026-11-13:
"collision meshes", "primitive colliders", "convex hulls", "collision mesh simplification", "collision checks",
"LOD setup"; the 3D methods audit, stages G1 and G2; his limitations page, D-R09).

Roblox makes a mesh's collision shape itself, from one of four settings (create.roblox.com, workspace/collisions,
read 2026-11-15), cheapest first:
    Box      "a bounding collision box, ideal for small or non-interactive objects"
    Hull     "a convex hull, suitable for objects with less pronounced indentations or cavities"
    Default  "an approximate collision shape that supports concavity, suitable for complex objects"
    PreciseConvexDecomposition  "the most expensive performance cost"
The choice is made here from what a PLAYER would feel: the empty space the cheaper shape would turn solid.
    - the mesh's box holds no empty space a stud across           -> Box
    - its convex hull holds none                                  -> Hull
    - a standing character passes into the hull's empty space     -> PreciseConvexDecomposition (a doorway, an arch,
      a room: the place must stay open exactly). The opening is 2 studs wide and 5 tall, and a stud deep - or right
      through the mesh where the mesh is thinner than a stud (a doorway in a thin wall)
    - anything else (dents and hollows a character cannot stand in) -> Default
Pure numpy on a grid of cells (the build fills `solid` from the mesh): no Blender here.

The level of detail: Roblox halves a mesh's triangles at 250 studs and again at 500 (RenderFidelity = Automatic) or
never (Precise). The build simulates both levels; here the surface's move is turned into PIXELS on a 1080-line
screen at those distances - Precise only when the move would be seen. NOT proven: the simulation is Blender's
decimator, not Roblox's; nothing here was looked at in Studio."""

import math

import numpy as np

NAMES = {"box": "Box", "hull": "Hull", "default": "Default", "precise": "PreciseConvexDecomposition"}
COST = ["Box", "Hull", "Default", "PreciseConvexDecomposition"]   # cheapest first
RENDER = {"automatic": "Automatic", "precise": "Precise", "performance": "Performance"}
ROOM = 1.0                 # studs: empty space this wide turned solid is felt (an invisible wall, a floating foot)
BODY = (2.0, 5.0, 1.0)     # studs (across, up, deep): a standing R6 character
CELLS = 96                 # cells along the longest side, at most
PITCH_MIN = 0.25           # studs: no finer than this (a small prop needs no finer grid)
FELT_CELLS = 2             # an empty space counts from this many cells across (one cell is the grid's own noise)
TRIS_FLOOR = 64            # under this many triangles a level of detail has nothing to reduce
SCREEN = 1080.0            # lines of the screen the pixels are counted on
FOV = 70.0                 # degrees, top to bottom (Roblox's default camera)
SEEN_PX = 1.5              # a surface that moves this many pixels is seen to move
LEVELS = ((250.0, "lod1"), (500.0, "lod2"))   # studs from the camera, the build's simulated level


def grid(lo, hi, cells=CELLS, pitch_min=PITCH_MIN):
    """the cells over a box lo..hi -> (pitch, (nx, ny, nz), centres (N, 3) in x-major order)"""
    lo, hi = np.asarray(lo, float), np.asarray(hi, float)
    span = np.maximum(hi - lo, 1e-9)
    pitch = max(float(span.max()) / cells, pitch_min)
    shape = tuple(int(max(1, math.ceil(s / pitch - 1e-9))) for s in span)
    axes = [lo[i] + (np.arange(shape[i]) + 0.5) * (span[i] / shape[i]) for i in range(3)]
    gx, gy, gz = np.meshgrid(*axes, indexing="ij")
    return pitch, shape, np.stack([gx.ravel(), gy.ravel(), gz.ravel()], axis=1)


def directions(n=258):
    """unit vectors spread evenly over the sphere, the six axes among them"""
    i = np.arange(n - 6) + 0.5
    phi = np.arccos(1 - 2 * i / (n - 6))
    theta = math.pi * (1 + 5 ** 0.5) * i
    ball = np.stack([np.cos(theta) * np.sin(phi), np.sin(theta) * np.sin(phi), np.cos(phi)], axis=1)
    axes = np.array([(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)], float)
    return np.vstack([axes, ball])


def in_hull(verts, pts, dirs=None, slack=1e-6):
    """which points lie inside the convex hull of verts (the hull as the planes that touch it in many directions:
    a hair larger than the true hull between two directions)"""
    verts, pts = np.asarray(verts, float), np.asarray(pts, float)
    dirs = directions() if dirs is None else dirs
    reach = (verts @ dirs.T).max(axis=0)                                  # the furthest the mesh goes each way
    inside = np.ones(len(pts), bool)
    for s in range(0, len(dirs), 32):                                     # (in slices: the grid is large)
        inside &= ((pts @ dirs[s:s + 32].T) <= reach[s:s + 32] + slack).all(axis=1)
    return inside


def _sums(a):
    s = np.zeros(tuple(n + 1 for n in a.shape), np.int64)
    s[1:, 1:, 1:] = a.astype(np.int64).cumsum(0).cumsum(1).cumsum(2)
    return s


def fits(empty, k):
    """does a block of k = (kx, ky, kz) cells fit wholly inside the empty cells?"""
    kx, ky, kz = (int(v) for v in k)
    nx, ny, nz = empty.shape
    if kx > nx or ky > ny or kz > nz or not empty.any():
        return False
    s = _sums(empty)
    block = (s[kx:, ky:, kz:] - s[:-kx, ky:, kz:] - s[kx:, :-ky, kz:] - s[kx:, ky:, :-kz]
             + s[:-kx, :-ky, kz:] + s[:-kx, ky:, :-kz] + s[kx:, :-ky, :-kz] - s[:-kx, :-ky, :-kz])
    return bool((block == kx * ky * kz).any())


def largest_cube(empty):
    """the side, in cells, of the largest cube of empty cells"""
    k = 0
    while k < min(empty.shape) and fits(empty, (k + 1,) * 3):
        k += 1
    return k


def _cells(studs, pitch):
    return max(1, int(math.ceil(studs / pitch - 1e-9)))


def _room(empty, p):
    """is there an empty space ROOM studs across (and at least FELT_CELLS cells: never one cell of noise)? Where
    the mesh is thinner than that, right through it (a window in a thin wall)"""
    return fits(empty, tuple(min(max(FELT_CELLS, _cells(ROOM, p[i])), empty.shape[i]) for i in range(3)))


def _passes(empty, p):
    """does a standing character pass into the empty cells? 2 across, 5 up, and a stud deep - or right through the
    grid where the mesh is thinner than a stud. Tried facing along x and along z (y is up)."""
    up = _cells(BODY[1], p[1])
    for across, deep in ((0, 2), (2, 0)):
        k = [0, up, 0]
        k[across] = _cells(BODY[0], p[across])
        k[deep] = min(_cells(BODY[2], p[deep]), empty.shape[deep])
        if fits(empty, k):
            return True
    return False


def measure(solid, hull, pitch):
    """solid, hull: (nx, ny, nz) bool - the cells the mesh fills, the cells its convex hull fills. pitch: studs a
    cell (per axis, or one number). -> what each cheaper shape would turn solid"""
    solid, hull = np.asarray(solid, bool), np.asarray(hull, bool) | np.asarray(solid, bool)
    p = np.broadcast_to(np.asarray(pitch, float), (3,))
    side = float(p.min())                                      # (a cube of cells is at least this wide in studs)
    in_box, in_hull_ = ~solid, hull & ~solid
    return {
        "pitch": round(float(p.max()), 4),
        "fill_box": round(float(solid.mean()), 4),
        "fill_hull": round(float(solid.sum() / max(1, hull.sum())), 4),
        "gap_box": round(largest_cube(in_box) * side, 3),      # studs: the widest empty cube inside the box
        "gap_hull": round(largest_cube(in_hull_) * side, 3),   # ... inside the convex hull
        "room_box": _room(in_box, p),                          # the box holds an empty space that is felt
        "room_hull": _room(in_hull_, p),                       # ... the convex hull does
        "body_box": _passes(in_box, p),                        # a standing character passes into the box's empty space
        "body_hull": _passes(in_hull_, p),                     # ... into the hull's
    }


def choose(m, size=None):
    """the cheapest setting that turns no felt empty space solid -> (Roblox's name, why in words)"""
    if size is not None and max(size) < ROOM:
        return "Box", f"under {ROOM:g} stud across: its box is all a player can feel"
    if not m["room_box"] and not m["body_box"]:
        return "Box", f"its box holds no empty space {ROOM:g} stud across (widest {m['gap_box']:g})"
    if not m["room_hull"] and not m["body_hull"]:
        return "Hull", (f"its box would add {m['gap_box']:g} studs of empty space; its convex hull adds none "
                        f"{ROOM:g} stud across (widest {m['gap_hull']:g})")
    if m["body_hull"]:
        return "PreciseConvexDecomposition", ("a standing character passes into a space its hull would close (a "
                                              "doorway, an arch, a room): that space must stay open exactly")
    return "Default", (f"a hollow {m['gap_hull']:g} studs across that no character stands in: an approximate "
                       "concave shape")


def judge(declared, m, size=None):
    """a setting the build script DECLARED, held against the mesh -> None | (level, what is wrong, the fix)"""
    chosen, why = choose(m, size)
    if declared == chosen:
        return None
    if declared in ("Box", "Hull") and m["body_hull" if declared == "Hull" else "body_box"] and chosen != "Box":
        return ("error", f"declared {declared}, but a standing character passes into a space that shape closes",
                f"a.collision(..., \"{[k for k, v in NAMES.items() if v == chosen][0]}\") - or leave it to the rule "
                f"({chosen}: {why})")
    if COST.index(declared) > COST.index(chosen):
        return ("warn", f"declared {declared}, the mesh needs no more than {chosen} ({why})",
                "drop the declaration: the cheaper shape feels the same and costs less")
    return ("warn", f"declared {declared}, the rule says {chosen} ({why})",
            "say so on purpose only for a thing no player touches")


def px_per_stud(distance, screen=SCREEN, fov=FOV):
    """how many screen lines one stud covers at a distance (studs) from the camera"""
    return screen / (2.0 * distance * math.tan(math.radians(fov) / 2.0))


def render_choice(moves, tris=None):
    """moves: {"lod1": studs the surface moves at Roblox's first level, "lod2": at its second} (95% of the surface,
    SIMULATED by Blender's decimator). tris: the mesh's triangles. -> (Roblox's RenderFidelity, why, {level: px})"""
    px = {lvl: round(float(moves.get(lvl, 0.0)) * px_per_stud(dist), 2) for dist, lvl in LEVELS}
    if tris is not None and tris < TRIS_FLOOR:
        # (halving a mesh of a few dozen triangles in the simulation wrecks it: that says nothing of Roblox)
        return "Automatic", f"{tris} triangles: a level of detail has nothing to reduce", px
    seen = [f"{px[lvl]:g} px at {dist:g} studs" for dist, lvl in LEVELS if px[lvl] >= SEEN_PX]
    if seen:
        return "Precise", (f"the simulated levels of detail move its surface {', '.join(seen)} "
                           f"(seen from {SEEN_PX:g} px)"), px
    return "Automatic", (f"the simulated levels move its surface {px['lod1']:g} px at 250 studs, {px['lod2']:g} px "
                         f"at 500: under the {SEEN_PX:g} px that is seen"), px


def columns(shape, axis):
    """the grid's columns along one axis -> (the two other axes, their cell counts)"""
    others = [i for i in range(3) if i != axis]
    return others, (shape[others[0]], shape[others[1]])


def fill_column(n, lo, step, hits):
    """ONE column of n cells from lo, step apart, crossed by a ray: hits = [(distance along the ray from lo, +1
    going IN through a face, -1 coming OUT)]. -> (inside: the winding number is not zero at the cell's centre - a
    cell inside two parts that overlap is inside; on: a face lies in the cell)"""
    inside, on = np.zeros(n, bool), np.zeros(n, bool)
    if not hits:
        return inside, on
    hits = sorted(hits)
    at = np.array([h[0] for h in hits], float)
    wind = np.cumsum([h[1] for h in hits])
    centres = (np.arange(n) + 0.5) * step
    before = np.searchsorted(at, centres, side="right")                  # hits behind each centre
    inside = np.where(before > 0, wind[np.maximum(before, 1) - 1], 0) != 0
    cell = np.clip((at / step).astype(int), 0, n - 1)
    on[cell] = True
    return inside, on
