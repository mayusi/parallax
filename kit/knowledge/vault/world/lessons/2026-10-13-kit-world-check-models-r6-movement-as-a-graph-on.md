---
kind: lesson
area: world
date: 2026-10-13
by: mayusi
source: "kit/lessons/world.md"
links: ["[[world/index]]"]
project: Parallax
---

kit world check models R6 movement as a graph on 1-stud voxels: a gap jump is not 'half the jump height at any distance' — use the real arc (v = sqrt(2 g J), g = 196.2, 16 st/s across: full J up to ~4.3 studs out, ~8.7 studs flat). Unreachable warnings must ignore thin strips (wall tops under 5 studs wide) and name each platform with bounds + height, or they cry wolf on every ring wall.
