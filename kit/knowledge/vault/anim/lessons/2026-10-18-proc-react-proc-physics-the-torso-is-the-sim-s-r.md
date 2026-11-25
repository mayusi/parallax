---
kind: lesson
area: anim
date: 2026-10-18
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

proc_react / proc_physics: the Torso is the sim's ROOT - a hit's spin on the Torso has no lever (spin 0-5 turned the body 17-23 deg); the body turn comes from a SOFT root: sim.root_rot_give is the stiffness factor during the hit, so LOWER = freer (0.1 + spin 9 -> 30 deg). An off-centre (Left Arm) impulse turned the body but killed the head snap (180 deg/s)
