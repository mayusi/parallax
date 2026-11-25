---
kind: lesson
area: vfx
date: 2026-11-13
by: mayusi
source: "kit/lessons/vfx.md"
links: ["[[vfx/index]]"]
project: Parallax
---

MEASURE how much of a drawn shape a sheet carries before calling it the scene's look (the owner on flame_arc, 2026-11-11: 'does not look like the thing', 'not high quality'). Read 2026-11-13 from the sheets as built: hk_tongue_gpu is a posterised simulation blob about 40 px across in a 256 px cell (2 % of the cell at its largest), hk_crescent a rendered glow whose halo became fat colour bands; neither has an outline, a cut-out or a sharp tip from the scene, and no check measured cell fill. My reading, not his words: part of that verdict is that the kit could not draw - its 'cel' sheets are simulations pushed through a posteriser. The scene's own drawings now come in as curves (kit vfx trace <set> --beat N --box ..., OPEN its pictures) and go out as a sheet (kit vfx ink <key> --from <trace.json>; its fill check refuses under 6 %). A whole key beat is a screen, not a card: frame ONE element.
