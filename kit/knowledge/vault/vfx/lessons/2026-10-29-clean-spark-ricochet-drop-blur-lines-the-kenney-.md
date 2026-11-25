---
kind: lesson
area: vfx
date: 2026-10-29
by: mayusi
source: "kit/lessons/vfx.md"
links: ["[[vfx/index]]"]
project: Parallax
---

Clean SPARK / ricochet / drop-blur lines: the Kenney kn_spark textures are zigzags and the fxlab 'rays' recipe paints a glowing source at its foot - both read as squiggles or white teardrops in flight. Use fxlab recipe 'streak' (sg_streak: a thin gaussian line, hot head near the top, tail fading down, square cell) on VelocityParallel sprites; measure a line texture's half-max width per row before using it (vfx-gt 2026-10-29).
