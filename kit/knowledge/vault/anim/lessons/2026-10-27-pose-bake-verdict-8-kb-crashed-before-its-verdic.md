---
kind: lesson
area: anim
date: 2026-10-27
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

POSE BAKE VERDICT > 8 KB = 'crashed before its verdict' (2026-10-27, SwordGuardBreak): pose_r6.py prints one JSON line with a note per key (an animated grip notes grip_turn_deg on EVERY key); past ~8 KB stdout's block buffer splits it and Blender's quit banner lands inside the line, so Run.content's lastJson finds no verdict though the bake passed. Workaround: fewer keys (key every 2nd frame, dense only where the curve matters - a floor-skimming tip); kit fix: flush + newline before quit, or drop zero-degree notes.
