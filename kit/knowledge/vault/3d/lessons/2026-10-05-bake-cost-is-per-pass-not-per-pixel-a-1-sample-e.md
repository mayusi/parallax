---
kind: lesson
area: 3d
date: 2026-10-05
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

Bake cost is per PASS, not per pixel: a 1-sample emission pass costs 0.3-1 s whatever it carries (M107: 109 passes = 63 s). Pack one-number channels three to a bake (R, G, B) and split - byte-identical, 63 -> 26 s. And 1-sample emission is faster on the CPU than the GPU (0.82 vs 0.92 s at 2048).
