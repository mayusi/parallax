"""build_protect.py — fixtures for A PLACE THE GAME VERSION MUST KEEP (a.protect; his D-R08: "Protect important
features and moving interfaces"; the 3D methods audit, stage L). A rippled plate of many triangles carrying one
patch of fine shallow grooves, built as a master and then as its game version (--optimize --budget=...). By the word after `--`:
  (none)   the grooves are named with a.protect: at a budget that flattens them otherwise, the decimator spares them. The
           game version must pass and say: protected: 1 of 1 places kept.
  watched  the same place only MEASURED (hold=False): the decimator is not steered, the grooves go, and the game
           version must FAIL `protected` by the place's name (build_protect_watched.py).
Used by `lune run kit selftest`. Never "fix" this file."""

import math
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
HOW = "watched" if "watched" in ARGS else "good"

N, HALF, BX, BZ, BR, DEEP = 96, 2.0, 1.2, 1.2, 0.4, 0.02


def top(x, z):
    y = 0.4 + 0.12 * math.sin(x * 3.0) * math.cos(z * 3.0)          # strong ripples: what a reduction keeps
    d = math.hypot(x - BX, z - BZ)
    # ... and fine shallow grooves in one place: what it drops first
    return y + (DEEP * math.sin(x * 37.7) * (1.0 - (d / BR) ** 2) if d < BR else 0.0)


verts, faces = [], []
for j in range(N + 1):
    for i in range(N + 1):
        x, z = -HALF + 2 * HALF * i / N, -HALF + 2 * HALF * j / N
        verts.append((x, top(x, z), z))
for j in range(N + 1):
    for i in range(N + 1):
        verts.append((-HALF + 2 * HALF * i / N, 0.0, -HALF + 2 * HALF * j / N))
T, B = (lambda i, j: j * (N + 1) + i), (lambda i, j: (N + 1) ** 2 + j * (N + 1) + i)
for j in range(N):
    for i in range(N):
        faces.append((T(i, j), T(i, j + 1), T(i + 1, j + 1), T(i + 1, j)))        # the top, facing up
        faces.append((B(i, j), B(i + 1, j), B(i + 1, j + 1), B(i, j + 1)))        # the underside, facing down
for k in range(N):
    faces.append((T(k, 0), T(k + 1, 0), B(k + 1, 0), B(k, 0)))                    # the four sides
    faces.append((T(k + 1, N), T(k, N), B(k, N), B(k + 1, N)))
    faces.append((T(0, k + 1), T(0, k), B(0, k), B(0, k + 1)))
    faces.append((T(N, k), T(N, k + 1), B(N, k + 1), B(N, k)))

a = rbx.Asset("_selftest_protect_" + HOW, tex=128, size=(4.0, 0.52, 4.0), bevel=0, stage="master")
a.material("cast", color=(0.45, 0.47, 0.5), metal=1.0, rough=0.5)
a.mesh("Plate", verts, faces, "cast")
a.protect("Grooves", (BX, top(BX, BZ), BZ), BR, within=DEEP / 4, hold=(HOW == "good"))
a.build()
