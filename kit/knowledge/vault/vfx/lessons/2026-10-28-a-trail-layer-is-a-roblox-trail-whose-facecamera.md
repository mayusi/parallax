---
kind: lesson
area: vfx
date: 2026-10-28
by: mayusi
source: "kit/lessons/vfx.md"
links: ["[[vfx/index]]"]
project: Parallax
---

A trail layer is a Roblox Trail whose FaceCamera defaults to TRUE in VfxStage (el.faceCamera ~= false) while the browser player draws trails FLAT - so a wide blade smear judged good in the player twisted toward the camera in the game (Sample Game 2026-10-28, the owner: the swings 'don't look proper'). For blade smears use trail "mesh": true (VfxMesh.ribbon: real swept geometry, UVs as the player's, alpha via SurfaceAppearance, surface = glow); it falls back to a FLAT Trail (FaceCamera false) where EditableMesh is off (vfx-gt 2026-10-28).
