---
kind: lesson
area: vfx
date: 2026-10-10
by: mayusi
source: "kit/lessons/vfx.md"
links: ["[[vfx/index]]"]
project: Parallax
---

Browser player: a sprite layer on an InstancedBufferGeometry must set geometry.instanceCount (and mesh.visible) every frame — mesh.count alone is ignored, so dead layers kept drawing their last particles as ghosts and two fresh judges called it 'the emitter never decays'. Probe liveness with window.kitPlayer().layers[i].live, never by eye alone.
