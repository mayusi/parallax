---
kind: lesson
area: 3d
date: 2026-10-21
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

When a model 'doesnt look polished and CLEAN', measure the TEXTURE before touching shape: Scarborough Fair's faces covered 4% of each 2048 map (smart_project's 0.01 island margin = ~20 px round each of thousands of islands: letters, trim curves, gem facets, chain links) -> 1.1 px/mm, everything baked blurry. The kit now projects with a 0.001 margin and repacks with Blender's concave packer + a 4-texel pad (42% coverage, 3.1x sharper; uv_coverage warns under 25%). And a stylised polished piece wants clean materials: no scanned scratch texture, edge_wear=0, edge_radius ~0.5 mm (the auto 0.55% of the asset was taller than its 0.85 mm inlays: they read melted).
