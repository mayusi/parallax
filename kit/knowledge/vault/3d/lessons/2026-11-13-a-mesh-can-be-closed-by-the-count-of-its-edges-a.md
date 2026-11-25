---
kind: lesson
area: 3d
date: 2026-11-13
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

A mesh can be closed by the count of its edges and still be no solid. Box modelling's first build pushed a pocket's floor outward and laid the new walls ON the pocket's own walls, looking the other way: every edge had two faces, the volume was right, and the next round tore it open. Count faces that lie on each other looking opposite ways as well as open edges, and refuse a push whose new wall would land on a wall that already runs the way the faces move (in at an outer edge, out at the foot of a wall)
