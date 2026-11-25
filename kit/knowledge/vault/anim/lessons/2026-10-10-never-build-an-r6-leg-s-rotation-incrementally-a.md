---
kind: lesson
area: anim
date: 2026-10-10
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

Never build an R6 leg's rotation incrementally (arc from the previous frame's direction): the R6 sole sits half a stud off the leg's axis (hip pivot on the outer top edge), so an accumulated twist walks the sole - a walk picked up 0.12 skid and 22-degree pops. Rotate from the rest direction each frame; pops at the antipode come from the source, not the fold.
