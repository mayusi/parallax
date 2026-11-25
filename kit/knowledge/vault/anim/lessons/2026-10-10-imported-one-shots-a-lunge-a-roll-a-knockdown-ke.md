---
kind: lesson
area: anim
date: 2026-10-10
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

Imported one-shots (a lunge, a roll, a knockdown) keep their travel as a ROOT track in the clip ([q, x, y, z] per frame); removing it linearly makes planted feet slide in the character frame. clip.py composes `root` into world_frames so the gates judge feet where the WORLD sees them; loops stay in place with locomotion.speed instead.
