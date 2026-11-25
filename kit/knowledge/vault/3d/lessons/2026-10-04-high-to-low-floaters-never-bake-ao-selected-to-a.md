---
kind: lesson
area: 3d
date: 2026-10-04
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

High-to-low (floaters): never bake AO selected-to-active when the high contains a copy of the low — Cycles evaluates it under the floater and bakes black wedges. Bake AO on the low with floaters as occluders and use a coverage mask (kit_floater attribute) for the footprints. Debug any bake with KIT_BAKE_DEBUG=1 (raw passes + measured quality views).
