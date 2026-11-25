---
kind: lesson
area: vfx
date: 2026-11-13
by: mayusi
source: "kit/lessons/vfx.md"
links: ["[[vfx/index]]"]
project: Parallax
---

Anything placed on the screen from a world point (a flare, a marker) must be placed AFTER the camera moves: the game's render step at Camera+2, the player's draw - an updater places it with last frame's camera and it slides on a shake
