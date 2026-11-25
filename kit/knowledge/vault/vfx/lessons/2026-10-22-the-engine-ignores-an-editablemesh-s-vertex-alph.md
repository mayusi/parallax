---
kind: lesson
area: vfx
date: 2026-10-22
by: mayusi
source: "kit/lessons/vfx.md"
links: ["[[vfx/index]]"]
project: Parallax
---

the engine ignores an EditableMesh's vertex alpha: anything that must appear / disappear along a mesh in-game (a slash drawing in, a wave collapsing) is done by moving vertices (the arc's sweep), never by vertex alpha (fadeIn/erode are player-only looks)
