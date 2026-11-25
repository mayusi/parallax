---
kind: lesson
area: 3d
date: 2026-10-05
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

The quality score's 'texture' was the 1-px Laplacian of the baked maps: it counted bake noise and never saw wood grain (a grained and a flat-painted twin scored the SAME, raw 42.9 — the old selftest only passed because the flat twin also lacked wear/grime). Texture is now the albedo a player sees: band-pass contrast at 2-18 px on crease-free surface (rbx_image.visible_texture). Lesson: a fixture pair must differ in ONE thing, or it tests something else.
