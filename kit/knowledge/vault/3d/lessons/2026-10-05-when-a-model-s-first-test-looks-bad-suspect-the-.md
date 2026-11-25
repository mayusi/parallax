---
kind: lesson
area: 3d
date: 2026-10-05
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

When a model's first test looks bad, suspect the test: BiRefNet scored IoU 0.29 against a 'non-white' mask of a transparent PNG (its hidden pixels are black, so everything was 'object'); against the real alpha it was 0.968. SAM's full-image box picks the BACKGROUND (score 0.99): prompt parts with points or tight boxes.
