---
kind: lesson
area: 3d
date: 2026-10-05
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

AO bakes see every part (contact shadows), so ANY geometry change makes every group's maps stale; a material-only change does not. Key bake caches as: whole-model geometry + per-group materials/settings. And fingerprint what ships (mesh arrays + map bytes), never FBX bytes - an FBX embeds its creation time, so every unchanged rebuild expired the judge's verdict.
