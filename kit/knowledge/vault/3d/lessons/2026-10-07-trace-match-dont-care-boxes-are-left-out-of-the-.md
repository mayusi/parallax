---
kind: lesson
area: 3d
date: 2026-10-07
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

trace_match dont_care boxes are left out of the FIT as well as the comparison: a big box (a whole nose) changed the outline's box and re-scaled the whole match (side_left IoU 0.97 -> 0.68). Keep each box to the small region that really differs (a corner), and never use one to hide a window you have not LOOKED at in the diff picture first.
