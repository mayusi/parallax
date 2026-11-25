---
kind: lesson
area: 3d
date: 2026-11-12
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

What Roblox KEEPS of an uploaded texture is seen only in Studio, never by downloading it: the plain download of an image asset (Open Cloud asset delivery) is a 1024 x 1024 copy whatever was sent, and softer than a native 1024, while the engine shows the 2048 or 4096 that was uploaded (test upload 2026-11-12: a stripe chart at three sizes on a slab, the camera 3 studs away at a 4 degree field of view; SurfaceAppearance.ColorMap and MeshPart.TextureID alike). To test a platform limit, upload a chart whose finest pattern only the full size can hold and look for that pattern.
