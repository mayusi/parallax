---
kind: lesson
area: anim
date: 2026-11-04
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

Re-BLOCKING a move after its base changes: kit anim edit <Move>Block keeps an existing <Move>Block.blend as the SOURCE (it says 'exists - it is already the source'), so the rebuilt key poses never reach the blocking render. Check the blend is unedited (git status / compare with its commit), remove it, then run edit again - never overwrite one the owner has touched
