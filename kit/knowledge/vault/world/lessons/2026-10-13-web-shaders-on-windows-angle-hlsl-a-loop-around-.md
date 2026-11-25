---
kind: lesson
area: world
date: 2026-10-13
by: mayusi
source: "kit/lessons/world.md"
links: ["[[world/index]]"]
project: Parallax
---

Web shaders on Windows (ANGLE -> HLSL): a loop around an expensive function, or texture2D (derivatives) inside a loop, is UNROLLED - kit world web's terrain shader took 42 s to compile. Fix: textureLod(...,0.) in loops, ONE call site for the expensive function (weights in a cheap loop, then surface() twice for the two strongest), fewer noise octaves, renderer.compileAsync. Time programs alone with gl.compileShader on a blank page before guessing.
