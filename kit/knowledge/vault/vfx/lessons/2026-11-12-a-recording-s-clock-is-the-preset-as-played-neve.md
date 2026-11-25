---
kind: lesson
area: vfx
date: 2026-11-12
by: mayusi
source: "kit/lessons/vfx.md"
links: ["[[vfx/index]]"]
project: Parallax
---

A recording's clock is the preset AS PLAYED, never the preset's file. kit vfx play writes the bundle it gives the player (build/vfx/play/<run>.json: the preset expanded - beats' names resolved to seconds, parts' and variants' layers and hit-stops in) before it records; denseclip.played() reads it. The file can say something else: starblade's has a hit-stop 'at': 'blast', and a tool that read its hit-stops from the file crashed - the dailies of every recorded play of such an effect, for hours, because the tool had only been tried on the piece it was written for. Try anything that reads presets on the most COMPOSED real one in the project (starblade: beats, use, variants, slow motion).
