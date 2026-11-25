---
kind: lesson
area: vfx
date: 2026-10-24
by: mayusi
source: "kit/lessons/vfx.md"
links: ["[[vfx/index]]"]
project: Parallax
---

Swarms were ERASED from every impact frame (fixed 2026-10-24 in the player): the frame pass hid SphereGeometry as sky (Ball swarms), dropped Box swarms as non-debris, and the ink override was multiplied by the swarm's per-particle colours (grey rocks inked at 0.36 < the 0.5 threshold). Embers / rocks / sand now draw into frames (and into baked frames). If a frame shows nothing of an element, debug the frame pass by reading its render targets (kit vfx play <name> without --record, window.kitPlayer(), seek, drawFrame, readRenderTargetPixels) - not by changing the preset.
