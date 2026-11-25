---
kind: lesson
area: 3d
date: 2026-10-05
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

Never min-max normalise a detector's output per image before a fixed threshold: TEED reads ANY flat surface as ~0.44 and real lines as 0.94-0.99, but stretched per image a flat grey slab became 97-100% 'line' (a perfect box-like model failed). Threshold the raw output at a fixed level (0.6), give the detector white paper around the object (pad), and erode masks with the outside counted as background. Prove every check BOTH ways: a positive fixture that must pass clean, not only a negative one.
