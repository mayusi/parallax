---
kind: lesson
area: 3d
date: 2026-10-27
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

Two export traps with downloaded meshes: (1) an image made with bpy.data.images.new + pixels + pack() exports into a GLB as ALL BLACK - write it to a PNG and load it back before export; (2) a low-poly tube (a sword grip) that shares a group with the collars it ends in comes out half inside-out after kit optimize's cut (normal fidelity p95 175 deg) - give it its own group (its own game mesh).
