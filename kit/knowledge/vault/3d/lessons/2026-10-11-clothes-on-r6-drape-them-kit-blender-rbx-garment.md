---
kind: lesson
area: 3d
date: 2026-10-11
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

clothes on R6: drape them (kit/blender/rbx_garment.py: tube -> drape -> finish), never type a box shell (owner: 'looks really bad'). Gotchas: a Hook modifier's empty must be PARENTED to the kit part (its world frame differs by BL_FROM_RBX's quarter turn: the hook turned and flung the end ring); a Solidify with use_even_offset on bunched cloth divides by the fold angle and flung a sleeve 88 studs (off + quality normals); bake the cloth headless by stepping scene.frame_set, not ptcache ops.
