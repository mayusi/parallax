---
kind: lesson
area: world
date: 2026-10-28
by: mayusi
source: "kit/lessons/world.md"
links: ["[[world/index]]"]
project: Parallax
---

Decor on a run wall must be out of raycasts, not just non-colliding: a ray-based wall run (side + diagonal rays, normal check) hits a thin inlay's SIDE and reads a sideways wall - SampleGame's run broke into 0.14-1.0 s pieces; with CanQuery off one 2.22 s run. Use "query": false on collide:false parts.
