---
kind: lesson
area: vfx
date: 2026-10-24
by: mayusi
source: "kit/lessons/vfx.md"
links: ["[[vfx/index]]"]
project: Parallax
---

A flipbook sprite that 'draws nothing' was a BROKEN SHEET, not the player: recipe import took ONE image with frames 16 as one frame and shrank the whole 4x4 sheet into cell 0 (cells 1-15 empty) - bloom_grow, frost_grow, kanada_flare (blade_glint in 4 originals) and the flowbake sheets played their full sheet tiny for one frame, then nothing (fixed 2026-10-24: one image + frames > 1 + grid = a sheet, sliced). Before blaming the player: check the BUILT png's cells (build/textures/<key>.png alpha per cell), then the sim (kitPlayer().seek(t), layer.live / iFrame) - a probe preset with a camera-facing control isolates it in one recording
