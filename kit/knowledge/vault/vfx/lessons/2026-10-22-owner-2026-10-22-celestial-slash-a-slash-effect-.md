---
kind: lesson
area: vfx
date: 2026-10-22
by: mayusi
source: "kit/lessons/vfx.md"
links: ["[[vfx/index]]"]
project: Parallax
---

owner 2026-10-22 celestial slash: a slash effect is built ON THE SWING - read the swordsman's facing + swing plane from the actor first (player.js pose(): faces -Z, pitches overhead -> 105 deg forward) and put the smear on the blade tip's path and the wave in that plane; cameras on / square to the axis. Use the library's impact_frames part AT THE HIT (the cut complete, the wave full size), never hand-made frames before the slash exists; soft glow sprites must start after the frames (they threshold into blobs that hide the slash); strike_air's horizontal swirls contradict a vertical cut (mute a, b, ring). Look at every texture before using it (pillar_glow is a square card)
