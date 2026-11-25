---
kind: lesson
area: vfx
date: 2026-10-22
by: mayusi
source: "kit/lessons/vfx.md"
links: ["[[vfx/index]]"]
project: Parallax
---

Give every GPU sim box headroom: a hot release overshoots its inversion (ceiling) - nk_mushroom2 at ceiling 0.55 still reached the top; 0.46 + sheet_end 0.7 left 23 %. kit/vfx/gpusim.py now WARNS when smoke enters the top / side edge-fade band (it reads as a cut). Fix with a taller res z, a lower ceiling or an earlier sheet_end - never by cropping the sprite.
