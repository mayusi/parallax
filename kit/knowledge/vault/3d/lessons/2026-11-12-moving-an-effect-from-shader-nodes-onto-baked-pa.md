---
kind: lesson
area: 3d
date: 2026-11-12
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

Moving an effect from shader nodes onto baked passes is only the same arithmetic where nothing CLIPS in between: a byte pass stops at 1 (a bright colour under a scan runs to 2.4 x its mean - the nodes darkened it before the clip, the pass clipped it first: 57 levels too dark) and at 0. Bake what lies over 1 as its own pass ((colour - 1) / 4) and add it back before multiplying. And check every OTHER writer of the number you now read: an imported mesh's record carried wear= from its life word for years with no nodes behind it - reading it would have mottled the dragon sword and the skull for the first time.
