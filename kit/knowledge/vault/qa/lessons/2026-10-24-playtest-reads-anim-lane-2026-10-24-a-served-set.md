---
kind: lesson
area: qa
date: 2026-10-24
by: mayusi
source: "kit/lessons/qa.md"
links: ["[[qa/index]]"]
project: Parallax
---

PLAYTEST READS (anim lane, 2026-10-24): a served set's hits signal runs IMMEDIATELY in some places - its handler sees the state BEFORE Moves applies the hit-stop / reaction (measured: speed 1 in the handler, 0 with 0.150 s left one task.defer later); read post-hit state in task.defer, and never sample 'the next frame' for a short effect: a background Studio server ticks every ~0.16 s, longer than a 0.15 s hit-stop
