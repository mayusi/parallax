---
kind: lesson
area: 3d
date: 2026-10-05
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

ONE SHAPE PER SEAM: when a part is cut out of a traced region (a magazine out of a receiver, a grip out of a frame), subtract it on the SAME raster (rbx_trace.region(..., minus=[(piece, gap_mm)])) and build the piece from that exact shape. Cutting with a separately simplified outline left ~1-3 mm shelves under the grip and the magazine (owner spotted them); building the magazine from a fitted quad while the receiver used the wavy trace left a 3 mm gap and then a collision.
