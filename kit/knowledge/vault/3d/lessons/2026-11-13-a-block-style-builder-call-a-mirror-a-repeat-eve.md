---
kind: lesson
area: 3d
date: 2026-11-13
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

A block-style builder call (a.mirror, a.repeat: everything made inside is copied) must keep the frame it was OPENED in. a.repeat first applied its row's step in the innermost a.frame open when each PART was made: a row opened outside a turned frame ran the wrong way and a ring turned about the wrong point. Store the block's own frame at entry and say its placements in the model's frame. Test every such call with a.frame opened inside it AND outside it
