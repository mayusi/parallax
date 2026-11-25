---
kind: lesson
area: anim
date: 2026-10-11
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

MOCAP TAKES: a research capture (Bandai Namco slash_normal) is a 17-20 s TAKE with 6 slashes and the actor walking the volume; imported whole it renders a dot in the corner (the look camera frames the whole root travel) and costs a 500-frame render. Cut single slashes first: right-hand speed > 12 studs/s merged within 0.3 s gives the segments (take 1: 2.33-3.23, 4.33-5.2, 8.07-8.8, 9.67-10.47, 13.83-14.73, 15.53-16.33 s); import each with `trim` [peak-0.45, peak+0.7].
