---
kind: lesson
area: vfx
date: 2026-11-10
by: mayusi
source: "kit/lessons/vfx.md"
links: ["[[vfx/index]]"]
project: Parallax
---

At the kit home, kit vfx <name> starts a 30-min clock for EVERY preset never recorded in assets/clocks/vfx/_built.json once any single look (kit vfx play) has recorded one piece there - lanecheck.prebuild_all treats a folder as 'already rebuilt' when it has any key. 2026-11-11 it clocked 119 old presets; the fix was to record every current digest (what a first full rebuild records) and delete the stray clocks. Before a first full rebuild: check _built.json covers the folder.
