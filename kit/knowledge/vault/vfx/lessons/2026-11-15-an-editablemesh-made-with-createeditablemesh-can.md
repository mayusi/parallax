---
kind: lesson
area: vfx
date: 2026-11-15
by: mayusi
source: "kit/lessons/vfx.md"
links: ["[[vfx/index]]"]
project: Parallax
---

An EditableMesh made with CreateEditableMesh can still grow, and a play client holds only 8 of those at once whatever their size (the ninth create returns nil, no error; the FixedSize option of an empty create is ignored). Grow it, copy it with CreateEditableMeshAsync(Content.fromObject(mesh), {FixedSize = true}) - same ids, positions / UVs / colours still move - and destroy the growable one at once; grow ONE at a time. A Studio PLAY client enforces the limit (edit mode and the server do not): it can be measured there
