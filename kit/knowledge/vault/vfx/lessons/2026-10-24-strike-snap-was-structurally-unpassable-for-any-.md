---
kind: lesson
area: vfx
date: 2026-10-24
by: mayusi
source: "kit/lessons/vfx.md"
links: ["[[vfx/index]]"]
project: Parallax
---

strike_snap was structurally unpassable for any hit whose impact-frame sequence starts ON the hit and lasts > 0.15 s: the frames' windows are excluded, so the first calm frame after them was always the 'peak' and the gate measured the frames' own length (seam: 0.32 s in every view, whatever changed). Fixed 2026-10-24 (player.js summarize): such a sequence is the strike held on the clock; the scene must reach 90 % within 0.15 s of the frames' END. Proven by kit/vfx/gates_test.cjs (a slow ramp AFTER the frames still fails). Lesson: when a gate value is IDENTICAL across views and rounds, reproduce the gate's computation from metrics.json before touching the effect.
