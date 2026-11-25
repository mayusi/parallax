---
kind: lesson
area: vfx
date: 2026-10-14
by: mayusi
source: "kit/lessons/vfx.md"
links: ["[[vfx/index]]"]
project: Parallax
---

Separating an aura from the character inside it: BiRefNet (kit vision cutout) counts the AURA as foreground - on SSJ stills 4515 of 4531 effect pixels fell inside its 'subject' mask (4 of 6 aura shots); subtracting it leaves nothing. Neither colour masks nor salient-object cutouts separate golden aura from golden hair; for aura OUTLINES pick full-body stills by eye (--pick) or try SAM with a point on the face + a negative point on the aura (not built).
