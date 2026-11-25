---
kind: lesson
area: 3d
date: 2026-10-10
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

The quality score's texture measure was FOOLED by broken UVs: a map with 0.11% coverage paints each triangle a random texel, and that speckle reads as 'visible texture' (the stump's texture 1.0 -> 0.94 once its UVs were real). When a score moves after a UV / bake fix, look at the model before trusting either number.
