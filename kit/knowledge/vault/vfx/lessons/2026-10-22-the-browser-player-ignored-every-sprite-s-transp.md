---
kind: lesson
area: vfx
date: 2026-10-22
by: mayusi
source: "kit/lessons/vfx.md"
links: ["[[vfx/index]]"]
project: Parallax
---

The browser player IGNORED every sprite's transparency curve from its first version (d2294774) until 2026-10-22: the shader wrote iMisc.w = 1 - transparency but never read it, so sprites stayed fully opaque and popped out at death. Effects judged in the player before 2026-10-22 had no sprite fades; re-record before comparing. Found when nuke_v4's surge, fully transparent by its curve, still showed.
