---
kind: lesson
area: world
date: 2026-10-24
by: mayusi
source: "kit/lessons/world.md"
links: ["[[world/index]]"]
project: Parallax
---

Blender cameras clip at 100 units by default: a horizon landmark 2000 studs away silently never renders (looked like 'haze ate it'). Set cam.clip_end >= 20000 for any vista frame; kit/world/frame_blender.py does.
