---
kind: lesson
area: anim
date: 2026-10-10
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

Putting a two-handed weapon into a finished R6 clip (kit/anim/rearm.py): keep the body, take the blade direction from the right arm (no wrist on R6: grip_pitch turns it), solve the off hand onto the hilt with the two-sphere solve, and give the steel MOMENTUM (a lag plus a one-pole inertia on hilt and direction). On a raw mocap whip (UAL2 Sword_Regular_A: the arm turns 75 degrees in a frame) the off hand snapped 152 degrees in one frame; with inertia 0.05 s it sweeps and passes the gates (pop bar 60 for a mocap body). Re-time Hits to the blade tip's peaks, one per strike.
