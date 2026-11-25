"""hlod.py - the far ranges as HLOD PROXIES (LIMITATIONS_FIXES_V3.md stage F.2: "batch far blocks into <= 2k-tri HLOD
proxy clusters replacing world.luau's cardboard wedges"). The horizon step stood each distant peak up as 4-8 wedge
parts (two back to back, crossed): a ring of 24 peaks was ~200 parts whose straight crests read as cardboard from the
spawn. A proxy is ONE mesh a quarter of the ring - a heightfield in polar cells, its skyline the sum of the same kind
of lopsided peaks - so the ring is four MeshParts (a MeshPart is 2048 studs a side at most: a ring 3000 across does
not fit one), each under MAX_TRIS. Pure python (no Blender): meshes_blender.py kind "hlod_ring" turns it into a mesh.

Frame: Roblox's own (x, y up, z), the ring's centre at the origin, its foot at y 0; quarter q (1..4) spans the
angles (q - 1) * 90 .. q * 90 degrees from +x toward +z. Neighbouring quarters share their seam's vertices exactly.
-> ring(spec, q) = (vertices [(x, y, z)], triangles [(i, j, k)] counter-clockwise seen from outside / above)."""
import math
import random

MAX_TRIS = 2000  # a proxy's budget (the V3 number)
MAX_SIDE = 2048.0  # studs: the most a MeshPart is along any axis (a quarter reaches out to the ring's outer foot)
STEPS_A = 48  # cells round a quarter
STEPS_R = 8  # cells from the ring's inner foot to its outer foot
FOOTHILL = 0.35  # the foothills' height, a share of the lowest peak's


def peaks(spec):
    """the ring's peaks: [(angle radians, radius, height, half-width radians)], the same for every quarter"""
    rng = random.Random(int(spec.get("seed", 1)))
    n = int(spec.get("count", 24))
    R = float(spec.get("radius", 1500))
    lo, hi = spec.get("height", [200, 500])
    out = []
    for k in range(n):
        a = (k + rng.random() * 0.6) / n * 2 * math.pi
        h = lo + (hi - lo) * rng.random()
        for j in range(2 + int(rng.random() * 2)):  # (2-3 peaks of falling height: the massif's skyline)
            hj = h * (1.0 if j == 0 else 0.45 + rng.random() * 0.35)
            out.append((a + (rng.random() - 0.5) * 0.12, R * (0.95 + rng.random() * 0.15), hj,
                        max(0.02, hj / R * (0.5 + rng.random() * 0.4))))
    return out


def foothills(spec, a, r, R):
    """the low band that joins the massifs (without it the skyline dropped to the ground between them, looked at
    2026-11-19): FOOTHILL of the lowest peak's height, rising and falling round the ring, highest mid-ring"""
    lo = float(spec.get("height", [200, 500])[0])
    seed = int(spec.get("seed", 1))
    across = max(0.0, 1 - abs(r - R) / (0.22 * R))  # (0 at the feet, 1 on the ring's middle line)
    wave = 0.75 + 0.25 * math.sin(7 * a + seed) * math.sin(3 * a + 2 * seed)
    return lo * FOOTHILL * across * wave


def height(ps, a, r, R, base=0.0):
    """the land's height at angle a, radius r: the highest of the peaks there (a peak falls off as a cone with a
    rounded top, across and along the ring) and the foothills under them, never below 0"""
    best = base
    for pa, pr, ph, pw in ps:
        da = math.atan2(math.sin(a - pa), math.cos(a - pa))
        across = abs(da) / pw
        along = abs(r - pr) / (pw * R * 1.6)
        d = math.hypot(across, along)
        if d < 1.0:
            best = max(best, ph * (1 - d) ** 1.3)
    return best


def ring(spec, q):
    R = float(spec.get("radius", 1500))
    r0, r1 = R * 0.78, R * 1.22
    if r1 > MAX_SIDE:
        raise ValueError(f"an HLOD ring of radius {R:.0f} is {r1:.0f} studs a quarter: a MeshPart is {MAX_SIDE:.0f} at most "
                         f"(a radius of {MAX_SIDE / 1.22:.0f} or less)")
    a0 = (q - 1) * math.pi / 2
    ps = peaks(spec)
    verts, tris = [], []
    for i in range(STEPS_A + 1):
        a = a0 + (math.pi / 2) * i / STEPS_A
        for j in range(STEPS_R + 1):
            r = r0 + (r1 - r0) * j / STEPS_R
            h = 0.0 if j in (0, STEPS_R) else height(ps, a, r, R, foothills(spec, a, r, R))  # (the feet on the far land)
            verts.append((r * math.cos(a), h, r * math.sin(a)))
    W = STEPS_R + 1
    for i in range(STEPS_A):
        for j in range(STEPS_R):
            v00, v01 = i * W + j, i * W + j + 1
            v10, v11 = (i + 1) * W + j, (i + 1) * W + j + 1
            # (facing up: angle grows from +x toward +z, radius outward - (v00, v10, v01) has its normal along +y)
            tris.append((v00, v10, v01))
            tris.append((v10, v11, v01))
    return verts, tris


def bounds(verts):
    lo = [min(v[k] for v in verts) for k in range(3)]
    hi = [max(v[k] for v in verts) for k in range(3)]
    return lo, hi
