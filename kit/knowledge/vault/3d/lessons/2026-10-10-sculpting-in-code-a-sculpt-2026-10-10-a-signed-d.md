---
kind: lesson
area: 3d
date: 2026-10-10
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

SCULPTING IN CODE (a.sculpt, 2026-10-10): a signed-distance field (rbx_sculpt, numpy) meshed by the OpenVDB Blender 5.x ships (openvdb.FloatGrid.convertToPolygons) is always ONE closed, manifold surface — no boolean to fail, no hole. Measured: a 20 mm ball within 0.07% of its volume, a torus keeps its hole, a 200 mm head at 0.5 mm voxels in ~8 s (blocks of 16 voxels culled by the field's slope, then again in 8s, noise only within reach of the surface: 58 s -> 8 s). Blender 5.2 also has SDF geometry nodes (SDF Grid Boolean / Fillet / Offset / Laplacian) if ever needed.
