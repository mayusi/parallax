---
kind: lesson
area: world
date: 2026-10-24
by: mayusi
source: "kit/lessons/world.md"
links: ["[[world/index]]"]
project: Parallax
---

Organic meshes (roots, bark, ropes) must not use the castle atlas's per-face random tile windows: every face picks its own window and the surface reads as a checkerboard. Use ONE tiling texture with continuous UVs (u around, v along, wrapping) - castle_blender.bark_texture + Mesh.quad_uv.
