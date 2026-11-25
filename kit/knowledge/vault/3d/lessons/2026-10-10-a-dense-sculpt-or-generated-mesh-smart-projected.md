---
kind: lesson
area: 3d
date: 2026-10-10
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

A dense SCULPT (or generated mesh) smart-projected loses its map: the relief turns the normal every few faces, the projection cuts thousands of islands and the packing margins swallow the rest — the tree stump's 482,876 triangles had 0.11% of their 2048 map (0.05 px/mm, its 6 mm end-grain rings 0.3 px). The kit now unwraps sculpt / dense imported faces by their FORM (rbx_uvcharts: six charts by the smoothed normal, conformal, packed): 1.19 px/mm, rings 7 px. A pattern under 4 px a cell is named (pattern_resolution).
