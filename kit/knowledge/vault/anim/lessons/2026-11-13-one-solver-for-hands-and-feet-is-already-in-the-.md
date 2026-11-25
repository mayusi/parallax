---
kind: lesson
area: anim
date: 2026-11-13
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

One solver for hands and feet is already in the strike builder, the R6 way: the hands reach the hilt by SLIDING the one-piece arms out of the shoulder (arm_slide 2.4 studs, as the loved R6 sword clips do), the legs point from the hips at planted feet and the pelvis sits over the weight foot, every frame. Measured 2026-11-14 on all 124 strike moves built here: 121 reach their designed grip exactly, the other 3 miss by 0.04 to 0.2 studs. A solver that moves the BODY to reach was not built: nothing needs it, and the loved cuts keep the body still (their bodies travel under 0.11 studs a second). Before building a method off a list, measure whether the builder already does it another way.
