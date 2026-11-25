---
kind: lesson
area: 3d
date: 2026-10-06
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

On a MASTER, floaters are the high-quality detail, not a bake: they stay real geometry in the group they decorate (checked like every part, so seat them) and are tagged kit_floater_onto for the game version. Conversely a GAME build's baked floaters must still count as the spec's parts (inspect never sees floaters: a rivet the spec names read 'missing'). Fixtures: build_master_floaters.py, build_game_floaters.py.
