---
kind: lesson
area: vfx
date: 2026-10-24
by: mayusi
source: "kit/lessons/vfx.md"
links: ["[[vfx/index]]"]
project: Parallax
---

A flat flipbook SPRITE (orientation VelocityPerpendicular, OneShot) drew nothing in the player's recordings - and one emitted at exactly t=0 drew the whole 4x4 sheet for a frame (moonflower, hoarfrost's centre patch); seek-time playback looked right. Until the player is fixed: grow things on the ground as stage DECALS crossfading in sequence (separate textures; decals keep alpha in the engine and draw reliably), and never start a flipbook burst at t=0. Open: the player bug itself (not yet diagnosed).
