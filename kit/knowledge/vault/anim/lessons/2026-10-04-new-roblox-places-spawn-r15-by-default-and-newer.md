---
kind: lesson
area: anim
date: 2026-10-04
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

New Roblox places spawn R15 by default (and newer avatars use AnimationConstraint joints, not Motor6D). kit anim now writes <Name> and <Name>_R15 from one spec; Anim.play picks by RigType — never assume R6.
