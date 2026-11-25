---
kind: lesson
area: 3d
date: 2026-10-16
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

Pixal3D hands back THICK HOLLOW shells: ~52% of its faces are an inner wall no outside ray reaches (barrel 143,949 of 278,676). The AO bake reads them as buried and multiplies the colour by 0.25 (extinguisher 171->43 red, black blotches on the barrel; owner 2/10 and 0/10 'colour and texture horrible'). Hunyuan's meshes have 0%. Measure hidden faces (26 + 40 ray directions) before blaming textures; make_clean --inner-wall drops them and caps the rims. Also: a public prop's generator texture is muddy - its colours only pick a kit finish per region (import_mesh regions=).
