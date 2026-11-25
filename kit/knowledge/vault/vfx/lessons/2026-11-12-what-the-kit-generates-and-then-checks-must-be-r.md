---
kind: lesson
area: vfx
date: 2026-11-12
by: mayusi
source: "kit/lessons/vfx.md"
links: ["[[vfx/index]]"]
project: Parallax
---

What the kit generates and then checks must be read right by the checker AS IT IS. The timing animatic put 0.7 of a beat's light on its hit drawing - exactly the share the timing read calls 'arrived' - and the read took the hit or the drawing after it by the luck of a blurred edge. 0.85 failed the same way: the read's floor (what is lit through nearly all of a stretch) can be the beat's own lead-in, and its line then sits at up to 0.85 of the whole light. Now the light is WHOLE on the hit drawing and at most 0.45 before it. Changing the checker for our own recordings (a lower floor) was tried and taken out the same day: it broke a glow that starts with the beat. And a mesh layer with a step (N drawings a second) changes only ON a drawing: put a hit, its keys and its hit-stop on the drawing grid, and put the stop INSIDE the hit drawing by the player's own sum, floor((stop - at) * step) - written in thousandths a hit can fall a hair before its drawing (0.175 - 0.05 is 0.12499999999999999 in a computer). Do NOT start the layer early instead: on a round time a frame's clock is a hair under it, and the beat was drawn a frame before its stretch.
