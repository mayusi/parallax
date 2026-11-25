---
kind: lesson
area: vfx
date: 2026-10-28
by: mayusi
source: "kit/lessons/vfx.md"
links: ["[[vfx/index]]"]
project: Parallax
---

CORRECTION to 'use trail mesh: true for blade smears': a game client holds only ~8 EditableMeshes in total (measured in Sample Game Play 2026-10-28: 8 small FixedSize meshes, then 'reaching memory budget limits' - EditableImage shares it), and a fresh build yields ~0.3 s. So smears are FLAT Roblox Trails (faceCamera: false), keep EditableMesh for a few hero shapes, prewarm those (Vfx.prewarm, pooled in VfxMesh) and use Slate chunks, not 'rock' debris. Measured too: a Roblox Trail maps its texture exactly as the player does (u = 1 at the newest point, the image's top at Attachment1) - a flat Trail IS the look judged in the player (vfx-gt 2026-10-28).
