---
kind: lesson
area: 3d
date: 2026-11-17
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

Roblox engine facts measured in Studio 2026-11-17 (KitPlaytestScratch, card fbvv/t5tr): a MeshPart's CollisionFidelity decides what a BODY touches, not what a RAY hits - rays pass where the mesh is drawn (an arch's doorway under Hull or Box closes it to a standing body, yet a ray through it hits nothing); on a simple arch Default and PreciseConvexDecomposition keep the doorway open, Hull and Box close it. Vertex colours are NOT drawn under a SurfaceAppearance (paint must be in the colour map). CreateMeshPartAsync takes {CollisionFidelity, RenderFidelity} exactly as asked and refuses an unknown key.
