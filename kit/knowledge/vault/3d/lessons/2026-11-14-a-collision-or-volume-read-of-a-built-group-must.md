---
kind: lesson
area: 3d
date: 2026-11-14
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

A collision or volume read of a built group must count faces IN and OUT along rays (the winding number), never the nearest face: kit models are overlapping parts in one group, and the nearest-face test read a solid block with a part sunk in it as hollow. Doorways are read as a body passing THROUGH the wall's thickness, not fitting inside it (walls are half a stud thick).
