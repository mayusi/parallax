---
kind: lesson
area: vfx
date: 2026-10-13
by: mayusi
source: "kit/lessons/vfx.md"
links: ["[[vfx/index]]"]
project: Parallax
---

an inflated back-face outline shell (player) must draw FIRST and write no depth (renderOrder below the object, depthWrite false) or it paints over the object: the ice read navy until this; debug the live player with window.kitPlayer() + readRenderTargetPixels
