---
kind: lesson
area: 3d
date: 2026-10-04
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

Small coloured details must have enough TEXELS: a model's groups share one texture, so a 0.045-stud letter got ~1.5 texels of stroke and baked as a smear (letters vanished). Lights + markings go in their own group (rbx_firearm does this as 'marks'); the texel_density gate fails hero/aaa builds where a high-contrast detail gets < 5 texels.
