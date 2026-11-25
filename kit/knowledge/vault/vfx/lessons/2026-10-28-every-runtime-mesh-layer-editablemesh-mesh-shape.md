---
kind: lesson
area: vfx
date: 2026-10-28
by: mayusi
source: "kit/lessons/vfx.md"
links: ["[[vfx/index]]"]
project: Parallax
---

Every runtime mesh layer (EditableMesh: mesh shapes, ribbons) needs the place's Experience Settings > Security > 'Allow Mesh & Image APIs' ON - off, CreateEditableMesh still RETURNS an object and the first AddVertex throws 'EditableMesh is not accessible' (so pcall the whole build, not just the create), and the layer draws nothing. Check it in a Play run before promising mesh VFX in a game: Sample Game had it off (vfx-gt 2026-10-28); turning it on is the owner's call.
