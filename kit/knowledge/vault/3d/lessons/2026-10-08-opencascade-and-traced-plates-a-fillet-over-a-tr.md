---
kind: lesson
area: 3d
date: 2026-10-08
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

OpenCASCADE and traced plates: a fillet over a traced part's whole perimeter is refused at every radius when tiny edges (0.1-0.3 mm, where a cut meets the outline) or unroundable neighbours break its tangent chains — round only the edges that read (the Glock trigger's face took 1.0 mm alone), and make every cut cross an outline at a clear angle from > 1 mm inside: a cut run along an outline leaves a 0.2 mm edge that the mesh bevel fallback folds into zero-area faces. And drop smooth_r when within= already re-fits the outline: clean_profile's arcs at every traced point block every fillet.
