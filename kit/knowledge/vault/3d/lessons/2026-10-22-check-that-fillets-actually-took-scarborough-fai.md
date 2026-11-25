---
kind: lesson
area: 3d
date: 2026-10-22
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

Check that fillets actually TOOK: Scarborough Fair's frame, hammer, spur and trigger tried radii 6..1.2 mm and NONE took (OpenCASCADE refuses fillets and solid offsets on traced, spline-fitted outlines) - a quiet try/except left every edge knife-sharp and the owner saw it ('guns ... are all smoothen out ... work on that'). Round such parts on the MESH: a.cad(..., round_mm=) bevels every edge sharper than 30 deg, 5 segments (frame 3.5 of 24 mm, spur 1.8 of 7, hammer 1.4 of 8: ~15% of the thickness).
