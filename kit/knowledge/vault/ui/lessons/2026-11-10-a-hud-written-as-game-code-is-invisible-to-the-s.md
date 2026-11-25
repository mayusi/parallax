---
kind: lesson
area: ui
date: 2026-11-10
by: mayusi
source: "kit/lessons/ui.md"
links: ["[[ui/index]]"]
project: Parallax
---

A HUD written as game code is invisible to the screen pipeline: Sample Game's ChamberHud sized itself at runtime (R2: HUD_SCALE 0.58 in its rescale()), every spec, compile and gauge stayed green, and the owner scored it 3/10 ('what the hell, I told you not this small'). A size floor in kit/ui/gauge.py was hollow because the HUD never ran through it. Give every game-code HUD a size contract (<root>assets/ui/huds/<Hud>.json: its code path, its own block helper and resize function, the owner-approved block sizes at 1080p with his words, a floor); kit ui hudsize and kit verify run the HUD's OWN helper calls and resize at 1920x1080 and desktop sizes and fail a block under floor x its reference. When the owner approves a HUD's size, record the measured blocks in its contract at once.
