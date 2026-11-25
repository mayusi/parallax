---
kind: lesson
area: 3d
date: 2026-10-08
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

Rounding a TRACED part in CAD: polygons for the booleans, then smooth_profile() as the sketch's last step (never clean_profile first: its arcs are tighter than the fillet). Bodies cut from one outline share ONE smoothed profile (smoothed apart, their walls nearly coincide and the join silently loses material); join curved bodies with .fuse(..., tol=0.1); extrude from the middle (both=True); fillet a body's long outer edges as ONE set; a cut that empties a joined part works on the one body it touches. Verify a join by inclusion-exclusion, not by eye.
