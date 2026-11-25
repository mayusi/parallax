---
kind: lesson
area: 3d
date: 2026-10-18
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

Roblox LOD facts (create.roblox.com, read 2026-10-18): no custom LOD meshes — RenderFidelity Automatic makes 3 levels itself (<250 / 250-500 / 500+ studs, each ~half the triangles), Precise never drops. kit optimize simulates both levels (facts.optimize.groups.<g>.lod); which RenderFidelity a mesh gets is said on every build (facts.fidelity.<g>.render, with render_px - corrected 2026-11-17, card fbvv). Textures: the texture-specifications page says 4096 in one section and 1024 for texture maps in another; the kit's game maps stay 1024 (safe either way); its guidance is ~51 px a stud (256 px for 5 studs), measured per build as facts.texel_density.
