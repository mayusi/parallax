---
kind: lesson
area: 3d
date: 2026-10-04
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

Game scripts CANNOT set SurfaceAppearance maps (Plugin capability) and nothing can set MeshPart.MeshId (measured). In game use Models.spawn/Models.tool: Rojo carries the maps (src/models/*.model.json), CreateMeshPartAsync makes the mesh. A SpecialMesh+TextureId gives colour only — that is why the first rifle looked flat.
