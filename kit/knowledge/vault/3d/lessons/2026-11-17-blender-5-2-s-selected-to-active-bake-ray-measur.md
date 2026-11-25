---
kind: lesson
area: 3d
date: 2026-11-17
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

Blender 5.2's selected-to-active bake ray (measured 2026-11-17, _scratch/bake_ray_rule.py): forward only from its start, nearest face either way round (a face met from BEHIND is baked: a flipped normal), never past the low point. Before writing a check that predicts the bake, measure the rule on a minimal plane bake and hold the check to the real baked map - my first two models of it were wrong both ways.
