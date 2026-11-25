---
kind: lesson
area: 3d
date: 2026-10-08
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

CORRECTION to the rounding lesson above: a fuzzy fuse (tol 0.1) of curved bodies DROPPED the Glock's whole trigger guard and left inside-out fragments, and 'keep the largest solid' hid it (the score said 85.5; only looking at the render showed the guard missing). Instead: build ONE solid = the smoothed side profile extruded once, intersected with a width ENVELOPE (loft + flat blocks); a part that must be rounded on its own (a guard) is its own body with its outline INSET ~0.15 mm so no wall coincides, joined plainly; and a CAD part that comes apart RAISES, never drops pieces in silence.
