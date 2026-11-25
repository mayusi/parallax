---
kind: lesson
area: 3d
date: 2026-11-10
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: sample_showcase
---

karambit 9/10 (owner in Blender, 2026-11-10: 'even in detail, it looks amazing. Textures look good'): a blade is a LOFT of ground sections, never an extruded outline - spine, swedge line, grind line and edge at 14 stations along two splines from a reference model's outline, the flats and the bevel as two solids sharing the grind line so each takes its own finish (black nitride flats, bright satin bevel: the value step draws the grind line). On the high-and-low route give every material its OWN group (several materials in one group make game_fidelity read one colour: albedo dluma 72 -> 2). Every finish a kit look with its scan: the first build's bare colours measured zero roughness variation on three of six. Build each side of a paired part on its own side (a mirrored CAD solid is not valid).
