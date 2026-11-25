---
kind: lesson
area: 3d
date: 2026-10-05
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

Studio renders: Cycles' OpenImageDenoise on the GPU (scene.cycles.denoising_use_gpu) gives the same picture (within 1/255, like a CPU rerun) 5x faster: 4.8 -> 1.0 s per presentation shot. Freestyle line art is the remaining cost (CPU, ~1.5-5.6 s per view, set by geometry, not resolution).
