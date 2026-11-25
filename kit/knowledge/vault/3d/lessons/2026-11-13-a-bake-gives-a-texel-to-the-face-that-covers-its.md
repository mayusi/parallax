---
kind: lesson
area: 3d
date: 2026-11-13
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

A bake gives a texel to the face that covers its CENTRE. A UV island thinner than a texel that starts on a texel's edge owns no texel and is drawn in a neighbour's margin colour - right or wrong by the luck of the layout (a 2 cm seam's wall on a 64 px map; a self-test passed for months by that luck, then failed when the layout moved 0.5%). When a thin dark part turns grey, count the texel centres each island covers (read the .blend's UVs) before touching the gate; the packer now lays an island in the middle of its texels (rbx_uvpack._centred).
