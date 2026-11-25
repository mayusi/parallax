---
kind: lesson
area: 3d
date: 2026-10-04
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

Never make two parts' faces coplanar (e.g. an end cap centred on a cylinder's end face): the AO bake treats each as occluding the other and bakes BLACK, which reads as a hole/open tube. Make one stand proud by a few thousandths.
