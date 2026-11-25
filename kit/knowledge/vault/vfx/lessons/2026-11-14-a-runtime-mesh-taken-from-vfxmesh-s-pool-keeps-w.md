---
kind: lesson
area: vfx
date: 2026-11-14
by: mayusi
source: "kit/lessons/vfx.md"
links: ["[[vfx/index]]"]
project: Parallax
---

A runtime mesh taken from VfxMesh's pool keeps whatever Size and Reflectance its last user gave it: read its own size from Built.native, never from part.Size, and give a varied set a FEW shared seeds (a seed a particle is a pool key a particle: 40 keys x 6 kept)
