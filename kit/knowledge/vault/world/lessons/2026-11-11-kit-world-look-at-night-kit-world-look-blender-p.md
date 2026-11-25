---
kind: lesson
area: world
date: 2026-11-11
by: mayusi
source: "kit/lessons/world.md"
links: ["[[world/index]]"]
project: Parallax
---

kit world look at night (kit/world/look_blender.py): a lamp's PointLight sits INSIDE its Neon head part, and in Blender's EEVEE that closed box shadows its own light completely - the first night render's lamps glowed but lit nothing. Roblox never lets a light's own part block it, so the look turns shadow casting off for every part that holds a light (object.visible_shadow = False) while the light keeps its shadows for everything else. Proof on a probe street: the wall beside each lamp 35 vs 23 between them. Any renderer of compiled worlds (frames, sheets) needs the same rule.
