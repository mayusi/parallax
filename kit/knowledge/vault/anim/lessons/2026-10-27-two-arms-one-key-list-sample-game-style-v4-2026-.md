---
kind: lesson
area: anim
date: 2026-10-27
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

TWO ARMS, ONE KEY LIST (Sample Game style v4, 2026-10-27): the pose route keys EVERY bone at EVERY key (merged_keys holds left-out fields), so two arms authored with different key times stall each other - an arm with no key at the other arm's key frame HOLDS there and then does its whole move in the remaining frames (a 4-frame throw run-up became a 1-frame jump). Author each arm on its own timeline and sample both every frame into joint keys with linear segments (_scratch/gt/gen_style4.py sample/bake); 2-frame sampling still stepped the velocity (constant over each pair) - key every frame.
