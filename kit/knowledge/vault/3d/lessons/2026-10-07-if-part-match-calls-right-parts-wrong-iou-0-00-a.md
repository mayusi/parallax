---
kind: lesson
area: 3d
date: 2026-10-07
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

If part_match calls right parts wrong (IoU 0.00, a slide '109 mm too tall') in a FULL build but not with --geo, suspect render state, not the model: a.project's render left the scene writing 16-bit PNGs (its settings' restore recorded the depth after the EXR format had already changed it) and the part-ID render decodes exact 8-bit colours. Fixed in the kit (snapshot-then-set restore, the ID render forces 8-bit; selftest part_match_depth16). Reproduce such bugs on build/models/<name>.blend headless in a minute instead of rebuilding.
