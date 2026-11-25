---
kind: lesson
area: vfx
date: 2026-10-25
by: mayusi
source: "kit/lessons/vfx.md"
links: ["[[vfx/index]]"]
project: Parallax
---

a mesh skin's v = 1 (a cone's tip, a crown's lip, a ring's outer edge) is the image's TOP row in both the engine (uv (u, 1 - v), top-left origin) and the player (flipY): build arrays row 0 = v 0 and flip on save, and give a skin wrapped round a closed shape post.border 0 or the border fade cuts a seam at u = 0 (skyfall)
