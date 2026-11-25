---
kind: lesson
area: anim
date: 2026-11-13
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

A quaternion forced to w >= 0 loses which way round a turn went: a share of a turn past 180 degrees then jumps by half a turn in one frame. Follow the run frame to frame (flip to the neighbour's side) before taking a share of it, and test with a 300 degree turn.
