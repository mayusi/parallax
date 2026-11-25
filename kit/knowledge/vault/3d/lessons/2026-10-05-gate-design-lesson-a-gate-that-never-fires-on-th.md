---
kind: lesson
area: 3d
date: 2026-10-05
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

Gate design lesson: a gate that never fires on the defect it was written for is worthless - prove each new gate on the broken model first (sliver, plate_support, marking_placement, attach_gaps all failed on the owner's defects before the fixes), then tune false positives with geometric meaning (parallel faces = shelf, flat back = plate, facing surfaces + no nearby contact = gap, small-on-big = seat), never with thresholds alone.
