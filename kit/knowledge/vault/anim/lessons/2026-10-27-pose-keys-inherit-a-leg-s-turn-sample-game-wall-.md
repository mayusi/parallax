---
kind: lesson
area: anim
date: 2026-10-27
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

POSE KEYS INHERIT A LEG'S TURN (Sample Game wall run, 2026-10-27): a pose_r6 key that leaves a foot's 'turn' out takes the LAST key's turn (merged_keys), so a loop whose step L key turns the left foot -10 ends 10 deg off its first frame (loop seam fail) - write turn 0 explicitly on every leg of a looped clip. And the planted-foot gate (CONTACT 0.04 over the rest sole) fails a DASH or a WALL RUN whose feet move along the clip floor: neither stands (170 studs/s; a wall run's feet are on the wall) - skim the burst / loop keys 0.06-0.08 off the floor instead of keying a fake plant
