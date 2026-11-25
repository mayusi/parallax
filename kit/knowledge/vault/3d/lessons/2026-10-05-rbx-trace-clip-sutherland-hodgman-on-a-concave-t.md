---
kind: lesson
area: 3d
date: 2026-10-05
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

rbx_trace.clip (Sutherland-Hodgman) on a concave traced outline leaves zero-width bridges and the extrusion collapses ('outlines do not overlap'); use rbx_trace.region() (raster + contour, cleaned at the photo's pixel size ~1 mm) - and clean() stairs off, or a slanted edge reads as a saw blade.
