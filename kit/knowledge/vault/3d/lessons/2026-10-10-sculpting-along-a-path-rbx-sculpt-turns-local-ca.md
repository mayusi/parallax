---
kind: lesson
area: 3d
date: 2026-10-10
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

Sculpting along a path: rbx_sculpt turns local -> canvas by Rx @ Ry @ Rz (CFrame order). To lay an ellipsoid's z along a direction D: rot=(atan2(-Dy, Dz), asin(Dx), 0) — checked exact on 7 directions; a yaw-only part whose WIDTH (x) runs along a heading phi (atan2(dx, dz)): rot y = phi - 90. Bone is a PLATE, not a tube: a jaw or a zygomatic arch as overlapping flattened ellipsoids along the path (step, length 1.6x the step), never s.stroke (round).
