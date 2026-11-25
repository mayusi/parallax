---
kind: lesson
area: 3d
date: 2026-10-16
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

Hole-fill faces made after a generator's UV atlas (make_clean holes_fill, _close_tears) have garbage corner UVs: single tiny faces spread across the WHOLE atlas (the extinguisher's covered it 6x over) and whatever bakes last wins - straight-edged steel rectangles / black triangles on the render. rbx._collapse_uv_giants collapses faces whose UV/3D area is >50x the median onto a neighbour's UV. Detect: sum of per-face UV area > 1, or a face with uv/3d ratio x1000 the median. A centroid-binned overlap probe MISSES it.
