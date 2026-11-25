---
kind: lesson
area: anim
date: 2026-11-14
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

A runtime matcher must be tested the way a game calls it: the pose on screen plus how it turned SINCE THE FRAME BEFORE, asked with the frame being played. Tests that fed the next frame's pose and a forward velocity passed while the real loop never advanced.
