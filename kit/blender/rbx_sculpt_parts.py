"""rbx_sculpt_parts.py — SCULPTED PART KITS: anatomy a sculpt keeps needing, as rbx_sculpt fields (mm, plain numpy).

A human skull built from balls and ellipsoids had BEAD TEETH ("uniform round beads like a string of pearls" — two
fresh judges, 2026-10-11): a real crown has its type's shape. Here each tooth is built from its type —
    incisor  a chisel: a flattened spade with a straight biting edge
    canine   a cone: one pointed cusp, the longest crown
    premolar two cusps (cheek-side and tongue-side) on a rounded body
    molar    a squarish block with four cusps
turned so its width runs along the arch, its biting end toward the other jaw.

    import rbx_sculpt_parts as SP
    t = a.sculpt("Teeth", "enamel", voxel_mm=0.35, mirror="x")
    t.add(SP.dental_arch(SP.ADULT_UPPER, y_occlusal=59, upper=True))
    t.add(SP.dental_arch(SP.ADULT_LOWER, y_occlusal=59, upper=False))
"""

import math

import numpy as np

import rbx_sculpt as S

# one side of an adult arch, front to back: (type, x, z) — x out from the midline, z back from the incisors' front
# (mm; the canvas frame: x right, y up, z back), and each type's crown (width along the arch, height, depth)
ADULT_UPPER = [("incisor", 4.4, -90.0), ("incisor_lateral", 12.0, -87.0), ("canine", 18.5, -81.5),
               ("premolar", 23.0, -74.0), ("premolar", 26.0, -66.5), ("molar", 29.0, -57.0), ("molar", 31.0, -46.5)]
ADULT_LOWER = [("incisor_lower", 2.8, -88.0), ("incisor_lower", 8.4, -86.5), ("canine", 14.5, -82.0),
               ("premolar", 19.5, -75.0), ("premolar", 23.0, -67.5), ("molar", 26.5, -57.5), ("molar", 29.0, -46.0)]
CROWN = {"incisor": (8.6, 10.5, 7.0), "incisor_lateral": (6.6, 9.0, 6.0), "incisor_lower": (5.2, 8.5, 6.0),
         "canine": (7.6, 11.0, 8.0), "premolar": (7.0, 8.0, 9.0), "molar": (10.0, 7.5, 10.5)}


def _yaw(prev, cur):
    """the turn (rbx_sculpt rot y, degrees) that lays a crown's WIDTH (its local x) along the arch from prev to cur:
    the tangent's angle from +z, less 90 (checked exact on rbx_sculpt.Ellipsoid)"""
    return math.degrees(math.atan2(cur[0] - prev[0], cur[1] - prev[1])) - 90.0


def _turn(v, yaw):
    """a local offset (x along the arch, y up, z across) turned by yaw about y — rbx_sculpt's Ry"""
    t = math.radians(yaw)
    x, y, z = v
    return (x * math.cos(t) + z * math.sin(t), y, -x * math.sin(t) + z * math.cos(t))


def crown(kind, c, yaw, down):
    """one tooth's crown field at c (its middle), its width along the arch (yaw), its biting end `down` (-1: toward
    -y, an upper tooth; +1: a lower one) -> a Node"""
    base = "incisor" if kind == "incisor" else kind
    w, h, d = CROWN[base]
    cx, cy, cz = c
    tip = lambda dx, dy, dz: tuple(a + b for a, b in zip((cx, cy, cz), _turn((dx, dy * down, dz), yaw)))  # noqa: E731
    rot = (0.0, yaw, 0.0)
    if base.startswith("incisor"):
        # a spade: a thin rounded slab, fuller toward the gum, its biting edge straight and narrow
        body = S.Box(c, (w, h, d * 0.55), round=min(w, d) * 0.22, rot=rot)
        bulge = S.Ellipsoid(tip(0, -h * 0.18, 0), (w * 0.5, h * 0.42, d * 0.5), rot=rot)
        return S.Union(body, bulge, 1.2)
    if base == "canine":
        # a cone: one pointed cusp at the biting end, a broad base at the gum
        cone = S.Capsule(tip(0, h * 0.42, 0), tip(0, -h * 0.2, 0), 1.2, w * 0.42)
        root = S.Ellipsoid(tip(0, -h * 0.22, 0), (w * 0.5, h * 0.35, d * 0.5), rot=rot)
        return S.Union(cone, root, 1.5)
    if base == "premolar":
        # two cusps across the arch on a rounded body
        body = S.Ellipsoid(c, (w * 0.5, h * 0.45, d * 0.5), rot=rot)
        cusps = S.Union(S.Ball(tip(0, h * 0.32, -d * 0.2), w * 0.24), S.Ball(tip(0, h * 0.3, d * 0.2), w * 0.22), 0.8)
        return S.Union(body, cusps, 1.0)
    # molar: a squarish block, four cusps on its biting face
    body = S.Box(c, (w, h * 0.8, d), round=min(w, d) * 0.28, rot=rot)
    node = body
    for sx, sz in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
        node = S.Union(node, S.Ball(tip(sx * w * 0.24, h * 0.36, sz * d * 0.24), w * 0.2), 0.9)
    return node


def dental_arch(teeth, y_occlusal, upper=True, gap=0.3):
    """one side of a jaw's teeth (a list like ADULT_UPPER), their biting ends meeting at y_occlusal -> one Node (mirror
    the canvas across x for the other side). gap: how neighbours meet — >= 0 (default): side by side as placed, each
    crown its own rounded shape (they touch at a point); < 0: FILLETED together by -2 x gap mm at their contacts, as
    real teeth touch (rounded crowns meeting at a point left dark slots between them: "beads", every judge)"""
    down = -1.0 if upper else 1.0
    node, prev = None, (0.0, teeth[0][2] - 1.0)
    for kind, x, z in teeth:
        base = "incisor" if kind == "incisor" else kind
        w, h, _d = CROWN[base]
        yaw = _yaw(prev, (x, z))
        prev = (x, z)
        cy = y_occlusal - down * h * 0.5
        t = crown(kind, (x, cy, z), yaw, down)
        node = t if node is None else S.Union(node, t, max(0.0, -2.0 * float(gap)))
    return node


def width_along(node, c, direction, reach=20.0, step=0.05):
    """a field's extent from c along a unit direction (both ways) -> mm: where d(p) changes sign (a test's measure)"""
    d = np.asarray(direction, dtype=float)
    d = d / np.linalg.norm(d)
    ts = np.arange(-reach, reach, step)
    p = np.asarray(c, dtype=float)[None, :] + ts[:, None] * d[None, :]
    inside = node.d(p) < 0
    if not inside.any():
        return 0.0
    idx = np.nonzero(inside)[0]
    return float(ts[idx[-1]] - ts[idx[0]])


# ------------------------------------------------------------------------------------------------ the face's parts
# Placed by LANDMARKS read off a reference (rbx_refmesh.landmarks), never by eye: a guessed bite plane 9 mm high made a
# skull's maxilla "a strip pasted under the cheek". Each takes the canvas, adds / carves its shapes (mirror the canvas
# across x for both sides) and returns it. Sizes in mm.

def orbit(s, centre, width, height, depth, rim=4.0):
    """an EYE SOCKET at `centre` (the rim's middle, its front plane): a rounded-square opening width x height,
    sinking `depth` back and narrowing toward the optic canal, its rim chamfered (a defined margin, not a fillet)
    and pinched along its upper-outer arc"""
    cx, cy, cz = centre
    # (the opening keeps its full size for its first 10 mm, as a real socket's walls run straight back before they
    #  narrow: a 10 mm box ending 3 mm into the face left a 15 mm half-width where it should be 20)
    s.box((cx, cy, cz + 3), (width, height, 22), round=min(width, height) * 0.28, carve=True, blend=rim * 0.3,
          edge="chamfer")
    s.ellipsoid((cx, cy, cz + depth * 0.45), (width * 0.48, height * 0.46, depth * 0.55), carve=True, blend=1.0)
    s.ellipsoid((cx * 0.9, cy - height * 0.05, cz + depth * 0.9), (width * 0.22, height * 0.22, depth * 0.3),
                carve=True, blend=1.0)
    arc = [(cx - width * 0.45, cy + height * 0.42, cz - 1), (cx, cy + height * 0.55, cz - 1.5),
           (cx + width * 0.48, cy + height * 0.25, cz - 1)]
    s.brush("pinch", arc, radius=rim, strength=0.5)
    return s


def nasal_aperture(s, floor_y, top_y, width, front_z, cavity=32.0, septum=True, spine=True):
    """the NASAL APERTURE: a tall pear from the nasal floor (floor_y) to under the nasal bones (top_y), widest a third
    of the way up, opening into a DEEP cavity (a 10 mm dish read as "a small round hole"); its septum recessed 4 mm
    inside, the anterior nasal spine at its foot"""
    h = top_y - floor_y
    s.ellipsoid((0, floor_y + h * 0.42, front_z + cavity * 0.35), (width / 2, h * 0.5, cavity), carve=True, blend=2)
    s.ellipsoid((0, floor_y + h * 0.82, front_z + cavity * 0.3), (width * 0.26, h * 0.22, cavity * 0.8), carve=True,
                blend=2)
    if septum:
        node = S.Box((0, floor_y + h * 0.5, front_z + 4 + 14), (2.6, h * 0.9, 28), round=1.0)
        s.add(node, 2.0, "septum")
    if spine:
        s.capsule((0, floor_y - 1, front_z + 6), (0, floor_y, front_z - 1.5), 3.2, 2.0, blend=4)
    return s


def mandible(s, chin, gonion, condyle, coronoid, thickness=12.0, ramus=6.0, height=26.0):
    """the MANDIBLE from its landmarks (right side; mirror the canvas): its body a plate from the chin round to the
    angle (gonion), the ramus a thin plate up from the angle forking into the condyle (to its joint) and the coronoid
    process (in front), the mandibular notch between them"""
    cx, cy, cz = chin
    gx, gy, gz = gonion
    mid = ((cx + gx) * 0.55, cy + (gy - cy) * 0.5, cz + (gz - cz) * 0.35)
    # (from PAST the midline: on a mirrored canvas the two halves overlap at the chin instead of touching)
    s.strap([(-thickness * 0.5, cy + height * 0.35, cz + thickness * 0.4), mid, (gx, gy + height * 0.2, gz)],
            [height, height * 0.95, height * 0.8], thickness, blend=6)
    s.strap([(gx, gy + height * 0.2, gz), (condyle[0], condyle[1] - 10, condyle[2])], [30, 14], ramus, blend=5)
    s.strap([(gx * 0.98, gy + 30, gz - 10), coronoid], [14, 5], ramus * 0.8, blend=3)
    s.ellipsoid(condyle, (10, 5, 7), blend=4)
    return s
