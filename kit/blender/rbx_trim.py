"""TRIM SHEETS AND A KIT OF MODULES (the owner's method lists, 2026-11-13: "trim sheets", "trim sheet UV mapping",
"seamless / tileable textures", "modular asset construction", "modular snapping"; the 3D methods audit, stage S2;
his limitations page D-R07: "family-wide trim / shared-atlas authoring was not found").

A TRIM SHEET is one texture many models share: bands laid one above another, each a strip of one finish (planks, a
steel edge, a row of rivets) that repeats along its length. A model that uses it bakes nothing of its own - its
faces are laid INTO a band, running along it as far as they are long (past the sheet's edge and round again) - so
a whole family of walls, rails and crates costs one texture's memory and reads as one material at one sharpness.

  layout(bands)                    where each band lies on the sheet (v0..v1), by its height in studs
  lay(points, faces, band, studs)  a whole PART laid into a band: U along it, V across the band, one run a side
  tileable_u(img, blend)           a baked sheet made to repeat along U (its two ends cross-faded)
  tile_step(img)                   how visibly a map fails to repeat along U (its left edge against its right)
  fit_problem(part, sides, band)   a side of the part pulled or squeezed past the limit across its band
  module_problem(size, at, grid)   a MODULE of a kit: its box a whole number of grid cells, its origin on the grid

Pure numpy: the build feeds it; no Blender."""

import numpy as np

GUTTER_PX = 4          # texels of each band's own colour repeated above and below it (bilinear and mip bleed)
STRETCH_MAX = 2.0      # a face may be this many times taller or shorter than its band before the build warns
TILE_SEEN = 12.0 / 255.0   # a step of colour across the sheet's wrap that is seen (as a texture seam: rbx_seams)
GRID_TOL = 0.02        # studs a module's size or origin may be off a whole number of cells


def layout(bands, px, studs, gutter_px=GUTTER_PX):
    """bands: [{"name", "height": studs}] top to bottom. px: the sheet's side in texels. studs: how much surface
    the sheet's WIDTH covers. -> {name: {"v0", "v1", "height"}} - each band's own strip of the map (v up, the
    first band at the top). Every band is laid at the sheet's ONE scale - its strip is height / studs of the map
    tall, so a texel is as tall as it is wide and every band is as sharp as every other - with a gutter of texels
    above and below it. The bands and their gutters must fit the sheet's height (its width again, in studs)."""
    if not bands:
        raise ValueError("a trim sheet needs at least one band")
    names = [b["name"] for b in bands]
    if len(set(names)) != len(names):
        raise ValueError(f"trim sheet: a band's name is used twice ({', '.join(sorted(names))})")
    heights = [float(b["height"]) for b in bands]
    if min(heights) <= 0:
        raise ValueError("trim sheet: every band has a height in studs, over 0")
    g = gutter_px / float(px)
    need = sum(heights) / float(studs) + 2 * g * len(bands)
    if need > 1.0 + 1e-9:
        over = (need - 1.0) * float(studs)
        raise ValueError(f"trim sheet: its bands are {sum(heights):g} studs tall with their gutters, {over:.2f} "
                         f"studs more than the sheet's {studs:g} - fewer or lower bands, or a sheet that covers "
                         "more studs")
    out, top = {}, 1.0
    for b, h in zip(bands, heights):
        span = h / float(studs)
        v1 = top - g
        v0 = v1 - span
        out[b["name"]] = {"v0": round(v0, 6), "v1": round(v1, 6), "height": h}
        top = v0 - g
    return out


def _unit(v):
    v = np.asarray(v, float)
    n = np.linalg.norm(v)
    return v / n if n > 1e-12 else v


def normal_of(pts):
    """a face's normal (Newell: any polygon, concave too)"""
    pts = np.asarray(pts, float)
    c = pts.mean(axis=0)
    n = np.zeros(3)
    for i in range(len(pts)):
        n += np.cross(pts[i] - c, pts[(i + 1) % len(pts)] - c)
    return _unit(n) if np.linalg.norm(n) > 1e-12 else None


def plane_dirs(n, along, up=(0.0, 1.0, 0.0)):
    """the two directions a face of a part is laid by -> (u, v), unit, in the face's plane.
    v is UP as near as the plane allows (so a finish is the same way up on the front of a wall and on its back -
    never turned over); on a face that looks up or down (a top, a floor) v runs square to the band's run.
    u runs along the band (`along`), never against it; on an end cap the band runs straight through, u is level.
    The two depend only on the face's normal, `along` and `up`: every face of one flat side gets the same pair."""
    n, along, up = _unit(n), _unit(along), _unit(up)
    v = up - n * float(up @ n)
    if np.linalg.norm(v) < 0.3:                                           # a top or a floor
        v = np.cross(up, along)
        v = v - n * float(v @ n)
    if np.linalg.norm(v) < 1e-6:                                          # (`along` is straight up: any level way)
        v = np.cross(n, (1.0, 0.0, 0.0) if abs(n[0]) < 0.9 else (0.0, 0.0, 1.0))
    v = _unit(v)
    u = _unit(np.cross(v, n))
    a = along - n * float(along @ n)
    if np.linalg.norm(a) > 1e-6:
        if float(u @ a) < 0:
            u = -u
    else:                                                                 # an end cap: one fixed way round
        k = int(np.argmax(np.abs(u)))
        if u[k] < 0:
            u = -u
    return u, v


def longest_axis(points):
    """the direction a part runs: the longest side of its box (x, y or z)"""
    pts = np.asarray(points, float)
    span = pts.max(axis=0) - pts.min(axis=0)
    d = np.zeros(3)
    d[int(np.argmax(span))] = 1.0
    return d


def lay(points, faces, band, studs, along=None, up=(0.0, 1.0, 0.0), start=0.0):
    """A WHOLE PART laid into a band. points: (N, 3) the part's points; faces: [[indices into points]].
    -> (uvs: one (len(face), 2) array a face, sides: [{"area", "across", "n"}] one a flat side of the part).
    Every face of one flat side is laid by the SAME two directions and from the SAME origin - the part's own
    lowest point along each - so a side split into several faces (a bevel strip, a window, a triangulated quad)
    carries ONE run of the finish: U goes on from face to face, V is the place across the band's height.
    U runs along the band at the sheet's scale (`studs` of surface across its width; past 1 and round again),
    from `start` studs; V fills the band over the part's whole extent across it. A face with no area gets the
    band's own corner."""
    pts = np.asarray(points, float)
    along = longest_axis(pts) if along is None else _unit(along)
    span = band["v1"] - band["v0"]
    uvs, sides = [], {}
    for f in faces:
        p = pts[list(f)]
        n = normal_of(p)
        if n is None:
            uvs.append(np.tile([start / float(studs), band["v0"]], (len(f), 1)))
            continue
        u, v = plane_dirs(n, along, up)
        key = tuple(np.round(np.concatenate([u, v]), 3))
        if key not in sides:
            su, sv = pts @ u, pts @ v                                     # the WHOLE part along this side's two ways
            sides[key] = {"u": u, "v": v, "u0": float(su.min()), "v0": float(sv.min()),
                          "across": float(sv.max() - sv.min()), "area": 0.0, "n": [round(float(c), 3) for c in n]}
        s = sides[key]
        e = p - p.mean(axis=0)
        s["area"] += 0.5 * float(np.linalg.norm(sum(np.cross(e[i], e[(i + 1) % len(e)]) for i in range(len(e)))))
        uu = (start + (p @ s["u"] - s["u0"])) / float(studs)
        vv = band["v0"] + ((p @ s["v"] - s["v0"]) / s["across"] if s["across"] > 1e-9 else 0.0) * span
        uvs.append(np.stack([uu, np.broadcast_to(vv, uu.shape)], axis=1))
    return uvs, [{"area": s["area"], "across": s["across"], "n": s["n"]} for s in sides.values()]


def fit(width, band):
    """how a side's extent across its band sits against the band's own height -> the stretch (over 1: the side is
    taller than the band, the finish is pulled tall; under 1: squeezed)"""
    return float(width) / float(band["height"]) if band["height"] > 0 else 0.0


SIDE_MIN = 0.25        # a pair of flat sides counts for the fit from this share of the part's surface: its broad
#                        faces - not a wall's narrow top, whose finish is squeezed but is a strip nobody reads


def fit_problem(part, sides, band_name, band, limit=STRETCH_MAX):
    """a part's flat sides against its band -> None, or the worst side that is pulled or squeezed past the limit
    (every pair of sides that is a quarter of the part's surface or more: its broad faces)"""
    total = sum(s["area"] for s in sides) or 1.0
    worst = None
    for s in sides:
        if s["area"] / total < SIDE_MIN:
            continue
        k = fit(s["across"], band)
        off = max(k, 1.0 / k) if k > 0 else 0.0
        if off > limit and (worst is None or off > worst[0]):
            worst = (off, k, s)
    if worst is None:
        return None
    off, k, s = worst
    how = "pulled tall" if k > 1 else "squeezed"
    return (f"{part}: its side facing ({', '.join(f'{c:g}' for c in s['n'])}) is {s['across']:g} studs across its "
            f"band \"{band_name}\" ({band['height']:g} studs tall): the finish is {how} {off:.1f}x - a band of "
            "that height, or the part split so each piece fits one")


def tileable_u(img, blend=0.125):
    """a baked map made to REPEAT along U. Near each end the map is cross-faded into ITSELF SHIFTED BY HALF ITS
    WIDTH: at the very ends only the shifted map shows, and there its two halves are neighbours - so the ends
    meet. The middle (all but `blend` of the width at each end) is not touched. img: (H, W, C). -> a new (H, W, C).
    (Use it only on a map that does not already repeat - tile_step says: the fade swaps a strip of the finish for
    another strip of it, which a band with one-off marks would show.)"""
    img = np.asarray(img, float)
    w = img.shape[1]
    k = max(1, int(round(w * blend)))
    x = np.arange(w)
    edge = np.minimum(x, w - 1 - x)                                       # texels to the nearer end
    keep = np.clip((edge + 0.5) / k, 0.0, 1.0)                            # 0 at the ends -> 1 inside
    shifted = np.roll(img, w // 2, axis=1)
    return img * keep[None, :, None] + shifted * (1 - keep)[None, :, None]


def tile_step(img, cols=2):
    """how a map fails to repeat along U: the mean colour of its last `cols` columns against its first, row by row
    -> {"step": the 95th percentile over the rows (0..1), "share": the share of rows whose step is seen}"""
    img = np.asarray(img, float)[..., :3]
    a = img[:, :cols].mean(axis=1)
    b = img[:, -cols:].mean(axis=1)
    d = np.abs(a - b).max(axis=1)
    return {"step": round(float(np.percentile(d, 95)), 4), "share": round(float((d > TILE_SEEN).mean()), 4)}


def module_problem(lo, hi, grid, tol=GRID_TOL):
    """A MODULE of a kit snaps to its neighbours: its box (lo..hi, in its own frame, studs) spans a whole number of
    grid cells on every axis the grid is given for, and starts on the grid - so its origin is a grid point and its
    far faces lie where the next module begins. grid: one number, or (x, y, z) with 0 for an axis left free.
    -> None, or what is off"""
    g = np.broadcast_to(np.asarray(grid, float), (3,))
    said = []
    for i, axis in enumerate("xyz"):
        if g[i] <= 0:
            continue
        size = hi[i] - lo[i]
        cells = size / g[i]
        if abs(cells - round(cells)) * g[i] > tol or round(cells) < 1:
            said.append(f"{size:g} studs along {axis} is {cells:.2f} cells of {g[i]:g}")
        off = lo[i] / g[i]
        if abs(off - round(off)) * g[i] > tol:
            said.append(f"it starts at {axis} = {lo[i]:g}, off the grid of {g[i]:g}")
    if not said:
        return None
    return ("a module does not snap: " + "; ".join(said) + " - size it in whole cells and build it from a grid "
            "point (its origin on a corner, or the middle of a face that is a whole number of cells)")


def cells(lo, hi, grid):
    """how many cells a module takes on each axis (0 where the grid leaves the axis free)"""
    g = np.broadcast_to(np.asarray(grid, float), (3,))
    return [int(round((hi[i] - lo[i]) / g[i])) if g[i] > 0 else 0 for i in range(3)]
