---
kind: lesson
area: vfx
date: 2026-11-13
by: mayusi
source: "kit/lessons/vfx.md"
links: ["[[vfx/index]]"]
project: Parallax
---

A runtime mesh built per piece takes a quarter second each: anything that builds many must be in Vfx.prewarm AND must swap in after the layer starts, or the first play shows stand-in blocks the player never showed
