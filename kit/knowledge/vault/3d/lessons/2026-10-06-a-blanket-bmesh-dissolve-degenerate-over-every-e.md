---
kind: lesson
area: 3d
date: 2026-10-06
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

A blanket bmesh dissolve_degenerate over every edge is not a cleanup: on a carved spine it tore 3 edges open and, run after a targeted pass, made a new zero-area face. Clamped bevels where several sharp edges meet (a pointed bar's tips on a curved band) leave faces 0.003-0.009 mm across, just above its 1e-5 tolerance: collapse ONLY the edges of faces under the validator's zero-area line (rbx._drop_micro_faces). Fixture: kit/selftest/blender/build_bevel_tip.py.
