---
kind: lesson
area: 3d
date: 2026-10-09
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

A generated model rendering as a see-through pencil sketch is a SHREDDED mesh, not a texture problem: a flat-shaded glTF is a triangle soup, and decimating the soup shreds it (the Glock's paint mesh had 51% open edges). Measure topology first (make.glb_topology: welded, a closed mesh has ~0 open edges and ~half as many vertices as faces).
