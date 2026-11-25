---
kind: lesson
area: vfx
date: 2026-10-16
by: mayusi
source: "kit/lessons/vfx.md"
links: ["[[vfx/index]]"]
project: Parallax
---

The game and the player disagreed on mesh texture v: three.js puts the image TOP at v = 1, Roblox EditableMesh at v = 0, and VfxMesh flipped only flame/tongue - so every other mesh texture (arc, ring, disc, sphere...) drew upside down in-game vs what the owner judged in the player. Fixed in VfxMesh (default grid 1 - v, scroll negated; planar keeps its projection). Author mesh textures with the image TOP = the shape's v = 1 side (an arc's OUTER rim); a verifier's 'detail on the wrong edge' is this trap. Found 2026-10-16 by the player verifier's detail crops.
