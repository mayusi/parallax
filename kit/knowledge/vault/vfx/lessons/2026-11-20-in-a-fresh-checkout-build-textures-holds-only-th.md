---
kind: lesson
area: vfx
date: 2026-11-20
by: mayusi
source: "kit/lessons/vfx.md"
links: ["[[vfx/index]]"]
project: Parallax
---

In a fresh checkout build/textures holds only the textures someone built there: a preset's 'glow' / 'spark' sprites drew NOTHING in the browser player (kit vfx play bundles only build/textures/<key>.png) and the recording still passed. Before judging a play, check the bundle (build/vfx/play/<name>.json textures) names every texture the preset uses; the kit's saved copy is library/vfx/textures/<key>/texture.png. Also: a recorded play of a SOUNDLESS preset was reported CONTENT ('OFF its sound') because Run.content is ok only on status pass and timing says 'unchecked' - fixed in content.luau (G2, 2026-11-20).
