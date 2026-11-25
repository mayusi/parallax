---
kind: lesson
area: 3d
date: 2026-10-18
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

kit optimize --retopo (Blender's QuadriFlow) vs the decimator at the SAME budget, the sculpted skull 146k -> 12k: QuadriFlow 0.76 mm p95 / 6.08 mm max from the master vs decimate 0.21 / 0.49 (the fidelity gate fails it); its wins are clean even quads (texel spread 1.18 vs 1.69) — use it for parts that DEFORM (skinned, animated), never for static props. QuadriFlow also refuses any mesh with an edge under 1e-4 units on every axis (its own zero-length test, reported as 'needs to be manifold'): the kit remeshes at x1000 and scales back.
