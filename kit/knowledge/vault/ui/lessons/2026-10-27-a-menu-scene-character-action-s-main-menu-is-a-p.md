---
kind: lesson
area: ui
date: 2026-10-27
by: mayusi
source: "kit/lessons/ui.md"
links: ["[[ui/index]]"]
project: Parallax
---

A menu SCENE (character-action's main menu is a photographed lamp-lit room): building it in-engine from parts in a place without Future lighting (local lights cast no shadows) read as a toy table (Sample Game 2026-10-27, measured mean luminance 8 vs character-action's 27-52). A Cycles still life layered for the engine worked: the frame lit + lamp-out as 2x2 tiles of 1024x576 (Roblox's 1024 cap), each moving object rendered ALONE as a sprite (rounds on a shadow catcher, the slide with everything else as holdout), positions from world_to_camera_view, and a virtual camera (canvas size + position) for push/pull shots. Generator: games/SampleGame/assets/ui/art/chamber/bench_render.py + bench_cut.py.
