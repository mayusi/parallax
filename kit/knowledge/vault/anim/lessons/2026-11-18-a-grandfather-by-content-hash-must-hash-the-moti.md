---
kind: lesson
area: anim
date: 2026-11-18
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

A grandfather-by-content-hash must hash the motion only: kit/anim/clip.py _clip_hash covers source.owner_rig (an absolute checkout path) and the rig/tool sha, so the same clip rebuilt in another checkout (the kit prove sandbox) misses its grandfathered hash and test_anim_switch_speed fails 2 cases on the committed tree (2026-11-18).
