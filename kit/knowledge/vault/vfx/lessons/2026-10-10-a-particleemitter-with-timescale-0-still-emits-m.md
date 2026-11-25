---
kind: lesson
area: vfx
date: 2026-10-10
by: mayusi
source: "kit/lessons/vfx.md"
links: ["[[vfx/index]]"]
project: Parallax
---

A ParticleEmitter with TimeScale 0 still EMITS (measured 2026-10-10: a captured moment reached through earlier freezes read 157 mean brightness vs 55 reached in one jump — rate emitters piled sprites up during every hold). Freezing a stage (hit-stop, capture holds, slow motion to 0) must also set Enabled = false on rate emitters; VfxStage does (emitter.want + clockRunning).
