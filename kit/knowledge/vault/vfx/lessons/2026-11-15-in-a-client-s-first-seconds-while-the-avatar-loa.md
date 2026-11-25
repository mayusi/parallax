---
kind: lesson
area: vfx
date: 2026-11-15
by: mayusi
source: "kit/lessons/vfx.md"
links: ["[[vfx/index]]"]
project: Parallax
---

In a client's first seconds (while the avatar loads) Roblox's CreateMeshPartAsync takes over a second a call: a mesh effect played then can be over before its meshes exist, with nothing refused. Play mesh effects after the character has loaded, or Vfx.prewarm. Ten cold sessions in one loop: StudioTestService:ExecutePlayModeAsync(args) in Edit returns what the server gives EndTest
