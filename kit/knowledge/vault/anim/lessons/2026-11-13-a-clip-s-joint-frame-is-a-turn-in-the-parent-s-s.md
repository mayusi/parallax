---
kind: lesson
area: anim
date: 2026-11-13
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

A clip's joint frame is a turn in the PARENT's space at rest, not Motor6D.Transform: the compiler turns it by c0. A rig whose c0 is turned (a built model's joint, its X the joint's axis) still takes poses about the real axis, and limits must be said in that space.
