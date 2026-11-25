---
kind: lesson
area: 3d
date: 2026-10-05
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

INTERNAL LINES: one edge detector (TEED, kit vision) on the reference photo AND on a shaded render of the model, compared in the same frame, sees what a silhouette cannot. A fixture with a perfect 1.0 silhouette IoU had 1% of the photo's inside lines; on the M107 it found the faint magazine ribs, the wrong A2 grip and a rail-base seam 5 mm off (59% of the photo's lines). Read build/renders/<asset>_lines_<view>.png every build.
