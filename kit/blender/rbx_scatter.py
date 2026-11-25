"""rbx_scatter.py — a moulded relief texture as REAL geometry: raised squares (a Glock Gen 5's grip), dots, studs on a
curved surface region, each seated on the surface by a ray (numpy only, tested without Blender; the rays and the
mesh: rbx.Asset.scatter_relief).

Why: a normal-mapped pattern cannot give each 2.2 mm square its own light and shadow — fresh judges read the Glock's
grip as "a flat, dark, printed dot patch" round after round (2026-10-09); a real moulded grip catches the light on
every square."""

import math

import numpy as np


def lattice(origin, u, v, pitch, half_u, half_v, rake_deg=0.0):
    """the points of a square lattice in the plane (u, v) through `origin`, `pitch` apart, covering a rectangle
    +-half_u along u and +-half_v along v (studs), the lattice itself turned by rake_deg in that plane (a grip's
    texture runs with the grip's rake) -> (N, 3) points, and the turned unit axes (a, b)"""
    o, u, v = (np.asarray(x, dtype=np.float64) for x in (origin, u, v))
    u, v = u / np.linalg.norm(u), v / np.linalg.norm(v)
    t = math.radians(rake_deg)
    a = math.cos(t) * u + math.sin(t) * v
    b = -math.sin(t) * u + math.cos(t) * v
    reach = math.hypot(half_u, half_v)
    n = int(math.ceil(reach / pitch)) + 1
    pts = []
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            p = o + a * (i * pitch) + b * (j * pitch)
            du, dv = float(np.dot(p - o, u)), float(np.dot(p - o, v))
            if abs(du) <= half_u and abs(dv) <= half_v:
                pts.append(p)
    return np.array(pts).reshape(-1, 3), a, b


def frustum(center, normal, axis, foot, top, height, sink):
    """one raised square frustum on a surface: its foot a `foot`-wide square `sink` below the surface point
    `center`, its top a `top`-wide square `height` above it, square to `normal`, its sides along `axis` (projected
    onto the surface) -> (8 verts, 6 faces: 4 sides, the top and the buried foot — a closed solid)"""
    c, n, ax = (np.asarray(x, dtype=np.float64) for x in (center, normal, axis))
    n = n / np.linalg.norm(n)
    x = ax - n * np.dot(ax, n)
    x = x / max(np.linalg.norm(x), 1e-12)
    y = np.cross(n, x)
    verts = []
    for z, w in ((-sink, foot / 2), (height, top / 2)):
        for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            verts.append(c + n * z + x * (sx * w) + y * (sy * w))
    faces = [(0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7), (4, 5, 6, 7), (3, 2, 1, 0)]
    return np.array(verts), faces
