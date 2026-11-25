---
kind: lesson
area: world
date: 2026-10-28
by: mayusi
source: "kit/lessons/world.md"
links: ["[[world/index]]"]
project: Parallax
---

Procedural Blender meshes for Roblox: give every face UVs projected on ITS OWN plane (studs / tile), bake the in-game placement scale into them, and pick the tile for the body scale (stone 8 = 2-stud courses; 16 gave 4-stud 'giant blocks' beside a 5-stud R6). Dominant-axis world UVs smear every moulding, roof and pinnacle into stripes - the owner's 'texture issues'. Audit: UV-area / face-area = (scale/tile)^2 per face.
