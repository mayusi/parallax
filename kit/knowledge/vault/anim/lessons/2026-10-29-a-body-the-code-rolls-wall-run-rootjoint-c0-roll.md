---
kind: lesson
area: anim
date: 2026-10-29
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

A body the CODE rolls (wall run: RootJoint C0 rolled 55 deg away from the wall) turns every body-frame hold: an arm 'held out' in the body hangs straight down in the world. Give such holds as WORLD directions converted through the roll, and render the frame from the game's camera with the roll applied before believing it (_scratch/gt/look_wall_tp.py).
