---
kind: lesson
area: 3d
date: 2026-10-10
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

A scan's NormalGL map is deliberately unused: scans are BOX-projected in object space, and a tangent-space normal map read through UV tangents points the wrong way there. The scan's HEIGHT as a bump (kit_scan_bump) is projection-independent and the bake carries it into the normal map under the rounded edges — raise relief= for more micro-relief, never wire the normal map in.
