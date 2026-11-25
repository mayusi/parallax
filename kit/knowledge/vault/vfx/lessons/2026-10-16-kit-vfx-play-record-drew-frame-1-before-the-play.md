---
kind: lesson
area: vfx
date: 2026-10-16
by: mayusi
source: "kit/lessons/vfx.md"
links: ["[[vfx/index]]"]
project: Parallax
---

kit vfx play --record drew frame 1 before the Player's textures had loaded (THREE.TextureLoader is async), so every layer in the first ~0.1-0.3 s of the FIRST recorded view recorded INVISIBLE - every player recording before 2026-10-16 11:30 lost its opening beat (flame_arc's ignition: 1 fire px -> 7415 at 0.04 s once fixed; 5 verifiers in a row said 'nothing burns at 0.09 s'). Fixed: the player tracks texture loads and record awaits texturesSettled() per view. When a verifier keeps naming an EMPTY opening, suspect the recorder before the effect.
