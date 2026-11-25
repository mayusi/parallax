---
kind: lesson
area: anim
date: 2026-10-11
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

FEEL: a body with the right poses and even mocap timing still reads as "horrible" on R6: the missing layer is TIMING, not poses. Finished R6 attacks (d5v set, Free Friday finisher, measured) hold 0.07-0.17 s before the strike, cross the strike in 1-2 frames (torso 1100-3300 deg/s = 40-110 deg in ONE frame), freeze 2-4 frames on the hit, overshoot and settle, then recover slowly over half the clip. `kit anim feel` applies exactly that to any clip; the pop gate must be lifted for the snap frame (it is a one-frame turn by design) - never "fix" the snap by easing it.
