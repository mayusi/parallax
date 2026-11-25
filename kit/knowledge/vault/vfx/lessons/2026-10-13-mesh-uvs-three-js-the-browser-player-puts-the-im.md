---
kind: lesson
area: vfx
date: 2026-10-13
by: mayusi
source: "kit/lessons/vfx.md"
links: ["[[vfx/index]]"]
project: Parallax
---

Mesh UVs: three.js (the browser player) puts the image TOP at v=1, Roblox EditableMesh at v=0 - an upright texture (flames) shows upside down and scrolls the other way in one of them. VfxMesh FLIP_V negates v (and the scroll) for flame/tongue; check any new shape whose texture has an up.
