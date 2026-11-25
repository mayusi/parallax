---
kind: lesson
area: 3d
date: 2026-11-11
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: sample_showcase
---

gjallarhorn_anniv (owner: 'horrible topology' -> 'Yes, retopo'): kit optimize --retopo on a master of ~90 separate CAD solids in 8 groups failed twice - default budget: 138-484 triangles a group, the surface up to 300 mm from the master; --budget 20000: 460-5,058 triangles a group, still up to 120 mm off (limit 3 / 14.6 mm). QuadriFlow remeshes each GROUP as one surface: many disjoint, thin, interpenetrating parts (lines, bands, screws, scroll wire) collapse. Clean topology for such a piece is not a pass after the fact: author it on the high-and-low route (Asset(low=...), each CAD part made twice, one group per material - the karambit, 9/10), or retopo only single-surface groups (--retopo wolf).
