---
kind: lesson
area: anim
date: 2026-10-27
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

pose_r6.py --check (no Blender) solves each arm against the STANDING rest body: on keys that drop / lean / turn the body (a slide, a dash) its hand_off numbers are meaningless (1.6 studs reported, 0.1 real) - bake to read the real offsets; and a generator placing feet / hands must put the hips and shoulders through pose_r6.body_rot (lean, turn AND tilt), or a tilted wall run slides a leg 0.3 deeper than asked (Sample Game movement set, 2026-10-27)
