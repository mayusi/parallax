---
kind: lesson
area: 3d
date: 2026-10-06
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

Generated meshes (kit gen / a.import_mesh): glTF stores a separate vertex wherever UVs or normals split, so a GLB arrives open along every seam (18,823 open edges on one TRELLIS.2 mesh) — import_mesh welds, closes pinholes and orients by signed volume; build them as a MASTER (100k+ tris) and let kit optimize make the game version.
