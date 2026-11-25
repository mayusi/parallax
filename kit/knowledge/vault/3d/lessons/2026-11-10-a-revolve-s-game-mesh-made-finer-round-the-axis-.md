---
kind: lesson
area: 3d
date: 2026-11-10
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

A revolve's GAME mesh made finer round the axis must take an angle limit (a.cad(..., low={'angle': 6})), never a finer tolerance: at low={'tol': 0.3} OpenCASCADE meshed each thin band of the car rim lip's profile rounds with its own count round the axis, the bands between counts became fans of twisted triangles 35-38 degrees off (over the low's 35-degree smoothing: a real crease), the lip failed its flat-map test and the baked normal map that took over striped its reflection again (2026-11-10, rework 6ebz). An angle limit gives every band the same count; it also costs more triangles than its segment count suggests (the lip: 2,804 -> 5,040 at 6 degrees).
