---
kind: lesson
area: 3d
date: 2026-10-06
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

Windows (WDDM) never says 'out of memory' when a GPU job outgrows the card: it spills into shared system memory and runs 4-20x slower (Pixal3D's 1024 shape stage: 22 min instead of 2). Peaks that matter are PyTorch's RESERVED memory, not allocated: torch.cuda.empty_cache() between the stages of a big generator (kit/gen/pixal3d_run.py does), and start GPU jobs only on an idle card.
