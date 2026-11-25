---
kind: lesson
area: 3d
date: 2026-10-04
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: sample_game
---

a.expect in_front_of/behind/above/below demand DISJOINT bounds, not just touching: a barrel seated into a receiver fails in_front_of. Use touches= for intentionally overlapping joints and save directional expects for truly separated parts (scope above body).
