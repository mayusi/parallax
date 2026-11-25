---
kind: lesson
area: vfx
date: 2026-10-14
by: mayusi
source: "kit/lessons/vfx.md"
links: ["[[vfx/index]]"]
project: Parallax
---

BROWSER PLAYER BUG fixed 2026-10-15: VelocityParallel laid the texture's X along the velocity, but Roblox (and every streak texture, drawn vertical; squash stretches along up) runs the texture's UP along it - every fast spark/shard/speed line in every effect rendered as a bar across its path (the 'barcode'). Re-record effects before judging their details.
