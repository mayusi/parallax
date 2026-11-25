"""quoins.py - a building's CORNER QUOINS as one instanced strip (LIMITATIONS_FIXES_V3.md stage B.1: "corner quoins as
instanced strips - never stripped like gothic_blender.py:551"). The whole-building skin (kind gothic_house) dropped its
quoins to stay under the mesh triangle cap; a strip is ONE storey of one corner - dressed stones, long and short in
turn, wrapping the corner and standing PROJ proud of both wall faces, a mortar JOINT between courses - made once and
placed at every corner of every storey of every skinned house (the compiler, kit/lib/world.luau: one mesh id, many
placements, so Roblox loads it once). Pure python (no Blender): gothic_blender.py turns the faces into a mesh.

Frame (Blender, Z up, 1 unit = 1 stud; the gothic set's own): the corner's foot is the ORIGIN; the building lies in
+X / +Y; the front face (Blender -Y, the skin's S side) is the plane y = 0 and the side face (-X) the plane x = 0.
-> faces: [(4 corner points, u axis, v axis, role)]: role k (the course's stone, 0 up) or "mortar" (the caulk set back
in a joint: without it the skin's own corner seam showed through every joint as a tick of light, looked at in the
built world 2026-11-19)."""
import math

PROJ = 0.15  # studs the stones stand proud of the wall
JOINT = 0.1  # studs of mortar between two courses (the wall's face shows through it, PROJ back)
COURSE = 1.4  # studs a course, near enough (the storey is cut into whole courses)
LONG, SHORT = 3.0, 1.8  # studs a stone reaches along a face, in turn
SETBACK = 0.1  # the mortar in a joint lies this share of PROJ out from the wall (set back from the stones' faces)


def courses(height, course=COURSE):
    """[(z0, z1)] the courses of one storey: whole ones, the first on the storey's foot and the last at its top"""
    n = max(1, int(round(height / course)))
    ch = height / n
    out = []
    for k in range(n):
        z0 = k * ch + (JOINT / 2 if k > 0 else 0.0)
        z1 = (k + 1) * ch - (JOINT / 2 if k < n - 1 else 0.0)
        out.append((z0, z1))
    return out


def strip(height, long=LONG, short=SHORT, proj=PROJ, course=COURSE):
    """the faces of one storey's strip (only what shows outside the wall: its back is in the wall)"""
    X, Y, Z = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)
    faces = []
    cs = courses(height, course)
    for k, (z0, z1) in enumerate(cs):
        lf, ls = (long, short) if k % 2 == 0 else (short, long)  # (along the front, along the side)
        p = -proj
        # the front face (y = -proj, facing -Y) and the side face (x = -proj, facing -X)
        faces.append(([(p, p, z0), (lf, p, z0), (lf, p, z1), (p, p, z1)], X, Z, k))
        faces.append(([(p, ls, z0), (p, p, z0), (p, p, z1), (p, ls, z1)], Y, Z, k))
        # the stone's two ends, where it meets the wall face (proj deep)
        faces.append(([(lf, p, z0), (lf, 0.0, z0), (lf, 0.0, z1), (lf, p, z1)], Y, Z, k))
        faces.append(([(0.0, ls, z0), (p, ls, z0), (p, ls, z1), (0.0, ls, z1)], X, Z, k))
        # its top and its underside, outside the wall (two pieces each, never overlapping: one plane, no flicker)
        faces.append(([(p, p, z1), (lf, p, z1), (lf, 0.0, z1), (p, 0.0, z1)], X, Y, k))
        faces.append(([(p, 0.0, z1), (0.0, 0.0, z1), (0.0, ls, z1), (p, ls, z1)], X, Y, k))
        faces.append(([(p, 0.0, z0), (lf, 0.0, z0), (lf, p, z0), (p, p, z0)], X, Y, k))
        faces.append(([(p, ls, z0), (0.0, ls, z0), (0.0, 0.0, z0), (p, 0.0, z0)], X, Y, k))
    # the mortar in each joint: set back, from the corner out as far as the shorter of the two stones either side
    m = -proj * SETBACK
    for k in range(len(cs) - 1):
        z0, z1 = cs[k][1], cs[k + 1][0]
        lf = min(long if k % 2 == 0 else short, long if (k + 1) % 2 == 0 else short)
        ls = min(short if k % 2 == 0 else long, short if (k + 1) % 2 == 0 else long)
        faces.append(([(m, m, z0), (lf, m, z0), (lf, m, z1), (m, m, z1)], X, Z, "mortar"))
        faces.append(([(m, ls, z0), (m, m, z0), (m, m, z1), (m, ls, z1)], Y, Z, "mortar"))
    return faces


def normal(pts):
    (ax, ay, az), (bx, by, bz), (cx, cy, cz) = pts[0], pts[1], pts[2]
    ux, uy, uz = bx - ax, by - ay, bz - az
    vx, vy, vz = cx - ax, cy - ay, cz - az
    n = (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
    m = math.sqrt(sum(c * c for c in n)) or 1.0
    return tuple(c / m for c in n)
