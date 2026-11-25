---
kind: lesson
area: 3d
date: 2026-10-21
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

kit optimize caps game maps at 1024 even when the master asked tex=2048: the main mesh splits into 4 maps for the same sharpness (_split_for_maps), and four separately decimated meshes drift further at the same triangle total (barrel 1.92 -> 2.46 mm p95) — give such a game version ~25% more budget (barrel: --budget 4600 -> 1.84 mm). The small-detail mesh gets a map sized to its smallest detail (barrel: 128, was a whole 1024).
