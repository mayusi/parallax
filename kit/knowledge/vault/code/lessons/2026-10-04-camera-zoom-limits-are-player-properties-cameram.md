---
kind: lesson
area: code
date: 2026-10-04
by: mayusi
source: "kit/lessons/code.md"
links: ["[[code/index]]"]
project: sample_game
---

Camera zoom limits are Player properties (CameraMinZoomDistance / CameraMode = LockFirstPerson), not Camera ones — setting camera.MinZoomDistance errors and kills the whole LocalScript. Re-read Workspace.CurrentCamera; it is replaced on respawn.
