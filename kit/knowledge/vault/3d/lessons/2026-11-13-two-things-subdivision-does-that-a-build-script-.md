---
kind: lesson
area: 3d
date: 2026-11-13
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

Two things subdivision does that a build script cannot see. It puts a face's new middle at the mean of its corners, so a face with a dent or many corners (what a.cut leaves round a hole, a rim's strips round a pocket) folds through its neighbours: split such faces first and hold a flat face's dividing edges with its outline. And Blender's crease number is not a scale: 0.5 and over is fully hard at two levels, so 0.6 and 0.7 changed nothing. Map your own 0..1 onto it by the level count and pin the result with measured volumes at 1, 2 and 3 levels
