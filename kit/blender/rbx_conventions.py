"""THE CONVENTIONS a model is held to on its way into the engine (the owner's method lists, 2026-11-13: "asset naming
conventions", "object naming", "pivot placement", "normal map convention", "import settings"; the 3D methods audit:
each was "written down, not checked by code").

Four small rules, pure Python - the build feeds them:
  names      a group and a material are named like an identifier the game can index: lowercase, digits, `_`
  pivot      the model's origin - where the game places it and where a hand holds it - lies on the model
  normal     the baked normal map is a tangent-space map (mostly blue where it is not flat fill), and the bake is
             TOLD the convention Roblox reads (OpenGL: +Y up)
  green      the map's own slopes say which way its green points: a real surface's slopes add up round any loop
             (no curl); read with the wrong green they stop adding up. Decided only when the map shows it clearly
             (curved or slanted relief); straight bevels along the map's axes show nothing either way (said)
  round trip the file the build exported, read back WITHOUT trusting the file's own axis header (Roblox ignores
             it), is the mesh it meant to export: the same triangles, size, place, every point where it was, and
             not inside out. NOT seen: the file's unit-scale header (Blender's importer always applies it).
What these do not prove is said beside each rule."""

import re

NAME = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
# the kit's own R6 outfit groups (src/kit/Models.luau R6_REST and the preview body): Models.wear looks them up by
# these exact names - they are the convention, not a breach of it
R6_GROUPS = ("Head", "Torso", "LeftArm", "RightArm", "LeftLeg", "RightLeg")
FLAT = 1.5 / 255        # a texel within this of (0.5, 0.5, 1) is the flat fill, not the surface's own normal
JUDGED_MIN = 0.01       # of the map that must be other than flat fill for its convention to be judged
PIVOT_OUT = 0.10        # of the model's diagonal the origin may lie outside its box
BLUE_MIN = 0.70         # a tangent-space normal map's mean blue over its own normals (a flat surface = 1.0)
SIZE_TOL = 0.002        # read back, a size or a place may differ by this share of the model's diagonal
NORMAL_SAID = "tangent space, OpenGL (+Y up): red +X, green +Y, blue +Z"
# the curl of the slopes read as OpenGL over the curl read as DirectX: below GREEN_GL the map is OpenGL, above
# GREEN_DX it is not; between, it does not show. Measured 2026-11-17 on the 295 baked normal maps in build/ (all
# baked OpenGL): 0.21 .. 1.38, median 0.81 - 55 decided, none wrongly; each of them with its green flipped: 55
# called DirectX, none wrongly. Scanned material maps decide far more often (a fabric weave 0.02, ivy leaves 0.04).
GREEN_GL = 0.6
GREEN_DX = 1.0 / GREEN_GL
GREEN_CELLS = 200       # fewer judged cells than this: nothing to decide from


def name_problem(kind, name):
    """kind: "group" | "material". -> None, or what is wrong with the name"""
    if NAME.match(str(name)) or (kind == "group" and str(name) in R6_GROUPS):
        return None
    why = ("starts with a letter" if not re.match(r"^[A-Za-z]", str(name)) else
           "is 32 characters at most" if len(str(name)) > 32 else "has no capitals, spaces or signs")
    return f"{kind} \"{name}\": a {kind}'s name {why} (lowercase letters, digits and _: the game indexes by it)"


def pivot_problem(lo, hi):
    """lo, hi: the model's box in ITS OWN frame (the origin is (0, 0, 0)). -> None, or how far outside the origin
    lies"""
    diag = sum((h - l) ** 2 for l, h in zip(lo, hi)) ** 0.5
    out = sum(max(l, 0.0, -h) ** 2 for l, h in zip(lo, hi)) ** 0.5       # distance from the origin to the box
    if diag <= 0 or out <= PIVOT_OUT * diag:
        return None
    return (f"the model's origin lies {out:.2f} studs outside the model (its box runs "
            f"({', '.join(f'{v:g}' for v in lo)}) to ({', '.join(f'{v:g}' for v in hi)})): the game places, turns "
            "and holds a model by its origin - build it round (0, 0, 0)")


def normal_problem(mean_rgb, judged=1.0):
    """mean_rgb: the normal map's mean red, green, blue over its texels that are NOT the flat fill (0..1); judged:
    the share of the map those are. -> None, or why it is not a tangent-space map in Roblox's convention.
    A map that is all flat fill has nothing to judge. NOT seen from a mean: a green channel flipped (the DirectX
    convention) - the build sets the bake's own convention instead (the manifest names what the bake was told)."""
    if judged < JUDGED_MIN:
        return None
    b = float(mean_rgb[2])
    if b < BLUE_MIN:
        return (f"its mean blue is {b:.2f} over the {judged:.0%} of it that is not flat fill (a tangent-space map "
                "is near 1 there too): an object-space map, a map with its channels swapped, or one that was "
                "colour-managed")
    # (red and green are NOT judged: a model bevelled on one side leans them for real - measured on a doorway)
    return None


def green_reading(rgb):
    """rgb: a normal map as an H x W x 3 array in 0..1, row 0 at v = 0 (Blender's pixel order; a PNG read top row
    first is flipped first). -> {"ratio", "cells", "reads": "opengl" | "directx" | None}: which way its green points,
    from the curl of its slopes both ways (a seam's jump and the flat fill are left out). None: it does not show."""
    import numpy as np  # noqa: PLC0415

    rgb = np.asarray(rgb, dtype=np.float64)[..., :3]
    n = rgb * 2.0 - 1.0
    nz = np.clip(n[..., 2], 0.25, None)
    gu, gv = -n[..., 0] / nz, -n[..., 1] / nz          # the height's slope along u and along v (OpenGL)
    own = (np.abs(rgb[..., 0] - 0.5) > FLAT) | (np.abs(rgb[..., 1] - 0.5) > FLAT) | (rgb[..., 2] < 1.0 - FLAT)
    cell = own[:-1, :-1] & own[1:, :-1] & own[:-1, 1:] & own[1:, 1:]
    du_v = gu[1:, :-1] - gu[:-1, :-1]
    dv_u = gv[:-1, 1:] - gv[:-1, :-1]
    keep = cell & (np.abs(du_v) < 0.5) & (np.abs(dv_u) < 0.5)
    cells = int(keep.sum())
    gl = float((((du_v - dv_u)[keep]) ** 2).sum())
    dx = float((((du_v + dv_u)[keep]) ** 2).sum())
    if cells < GREEN_CELLS or gl + dx <= 1e-9:
        return {"ratio": None, "cells": cells, "reads": None}
    ratio = gl / max(dx, 1e-12)
    reads = "opengl" if ratio < GREEN_GL else "directx" if ratio > GREEN_DX else None
    return {"ratio": round(ratio, 3), "cells": cells, "reads": reads}


def green_problem(rgb):
    """-> None, or why the map's green does not point the way Roblox reads it (OpenGL, +Y up)"""
    r = green_reading(rgb)
    if r["reads"] != "directx":
        return None
    return (f"its slopes add up only with the green flipped (curl {r['ratio']:.2f}x the other reading, over "
            f"{r['cells']} texels): a DirectX normal map - or one whose pixels were turned without its vectors. "
            "Roblox reads OpenGL (+Y up): flip its green (or bake it told OpenGL)")


def roundtrip_problem(meant, read, diag=None, far=None, inside_out=False):
    """meant, read: {"tris": n, "size": (x, y, z), "centre": (x, y, z)} of the mesh the build exported and of the
    file read back; far: the furthest any point of the mesh lies from where it was exported (None: not compared);
    inside_out: the read-back mesh encloses its volume the other way round. -> None, or what differs"""
    d = diag if diag else max(sum(v * v for v in meant["size"]) ** 0.5, 1e-9)
    if meant["tris"] != read["tris"]:
        return f"{read['tris']} triangles read back, {meant['tris']} exported"
    ratios = sorted(r / max(m, 1e-9) for m, r in zip(sorted(meant["size"]), sorted(read["size"])))
    if any(abs(a - b) > SIZE_TOL * d for a, b in zip(sorted(meant["size"]), sorted(read["size"]))):
        same = ratios[-1] - ratios[0] <= 0.01 * ratios[-1]
        return ((f"read back {ratios[-1]:g}x the size it was exported at" if same else "read back a different shape")
                + f" (({', '.join(f'{v:.3f}' for v in read['size'])}) against "
                f"({', '.join(f'{v:.3f}' for v in meant['size'])}) studs): the file's scale")
    if any(abs(a - b) > SIZE_TOL * d for a, b in zip(meant["size"], read["size"])):
        return (f"read back turned: its sizes along x, y, z are ({', '.join(f'{v:.3f}' for v in read['size'])}), "
                f"exported ({', '.join(f'{v:.3f}' for v in meant['size'])}): the file's axes")
    if any(abs(a - b) > SIZE_TOL * d for a, b in zip(meant["centre"], read["centre"])):
        return (f"read back at ({', '.join(f'{v:.3f}' for v in read['centre'])}), exported at "
                f"({', '.join(f'{v:.3f}' for v in meant['centre'])}): moved or mirrored on the way")
    if far is not None and far > SIZE_TOL * d:
        return (f"read back with its points up to {far:.3f} studs from where they were exported, in the same box: "
                "turned half round or mirrored on the way (it would face backwards in the game)")
    if inside_out:
        return "read back inside out (its faces wound the other way): mirrored on the way"
    return None
