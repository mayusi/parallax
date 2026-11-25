---
kind: lesson
area: code
date: 2026-10-04
by: mayusi
source: "kit/lessons/code.md"
links: ["[[code/index]]"]
project: sample_game
---

Lune headless specs have no Vector3 global (typeof(Vector3) is nil), so shared Rules must take plain {X,Y,Z} shapes that real Vector3s satisfy in game; enforce the real engine type server-side with Guard.vector3 before the Rules.
