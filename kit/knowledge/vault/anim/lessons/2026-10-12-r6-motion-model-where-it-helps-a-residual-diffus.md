---
kind: lesson
area: anim
date: 2026-10-12
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

R6 MOTION MODEL, WHERE IT HELPS: a residual diffusion model (x0 = keyframe fill + delta, kit/anim/motion_model.py v3, 50 min of native R6 data) matches slerp between keys 20 frames apart and beats it at 30+ on held-out locomotion (60 frames: 18.0 vs 24.4 deg). On held-out loved weapon attacks cut to 5 key poses, plain slerp WON (11.4 vs 21.8 deg): attack gaps are short and close to interpolation, and the one long gap (an 88-frame recovery) is where a combat-starved model invents motion. Ship the hybrid fill (motion_fill.py) for locomotion; for combat keep the human clip or slerp until there is more combat data. R6 clips run IN PLACE: 'foot planted' = the foot at the clip's own lowest height, never 'foot not moving'.
