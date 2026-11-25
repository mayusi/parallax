---
kind: lesson
area: 3d
date: 2026-10-16
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

A generated mesh with OPEN holes left after cleaning must never get a whole-mesh recalc_face_normals: on an open shell it guesses wrong (the made extinguisher came out 40-74% inward: black patches, inside_out gate). rbx._close_tears now recalculates only when its result is closed; otherwise each new fill face takes its neighbour's winding (_wind_like_neighbours). Check: signed volume after import vs the GLB's (0.0189 vs 0.198 = scrambled).
