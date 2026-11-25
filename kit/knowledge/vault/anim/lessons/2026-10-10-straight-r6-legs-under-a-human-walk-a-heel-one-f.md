---
kind: lesson
area: anim
date: 2026-10-10
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

Straight R6 legs under a human walk: a heel one frame before the plant must NOT count as standing (threshold 0.02 on the lowest edge, not the sole centre), the pelvis follows the foot that landed LAST, and the trailing standing leg slides up into the torso (a straight leg heel-rise) instead of digging in; one-frame flight phases need a finer time grid (MIN_FRAMES 20) or the pelvis spikes.
