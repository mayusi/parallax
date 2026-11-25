---
kind: lesson
area: vfx
date: 2026-11-16
by: mayusi
source: "kit/lessons/vfx.md"
links: ["[[vfx/index]]"]
project: Parallax
---

A Heartbeat step's dt is the whole PREVIOUS frame: a stage started inside a long frame (the avatar arriving hitches 0.3-1.3 s) jumped that far into its life on its first step. Bound a clock's step by the real time since the last step (os.clock), except while catching up on purpose
