---
kind: lesson
area: 3d
date: 2026-10-10
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

kit make --no-gen on a NATURAL object (a skull): found photos are different specimens, so tracing was skipped and nothing could give a shape (no candidate, nothing built). Now the best side + front photos are traced as SPECIMENS: they shape the clay (the hull), are matched by silhouette only (trace_match lines=False: another skull's seams are not this one's) and are never projected. The hull is only clay: the real model is sculpted in <name>.override.py (a.remove the hull, a.design['size'] from sourced sizes).
