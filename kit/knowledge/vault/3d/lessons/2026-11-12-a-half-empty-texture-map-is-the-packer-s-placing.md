---
kind: lesson
area: 3d
date: 2026-11-12
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

A half-empty texture map is the packer's PLACING, not its pads or its settings: before tuning anything, measure the pad-only bound (every island in its own outline plus half a pad) and run every packer setting once. On 33 groups of 15 built models the pads allowed 0.93 of the map and Blender's settings differed by a median 0.001, while the faces covered 0.55 - so the kit packs by shape itself (rbx_uvpack: the small islands in the holes the big ones leave; a median 0.55 -> 0.70, 11% more texels a metre from the same file). Built models' islands can be measured read-only from their .blend: no rebuild needed to test a packer.
