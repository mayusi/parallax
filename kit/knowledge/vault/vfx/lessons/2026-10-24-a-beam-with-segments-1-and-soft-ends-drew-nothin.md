---
kind: lesson
area: vfx
date: 2026-10-24
by: mayusi
source: "kit/lessons/vfx.md"
links: ["[[vfx/index]]"]
project: Parallax
---

A beam with segments 1 and soft ends drew NOTHING in the player (the soft-end fade sits on the vertex rows and a 1-segment strip has only end rows); fixed - the player now gives a soft-ended beam >= 8 rows. Also: a beam's color/transparency/width SEQUENCES run along its LENGTH (Roblox Beam), not over time - [[0, paper], [0.2, verm]] drew a pale paper beam.
