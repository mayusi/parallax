---
kind: lesson
area: vfx
date: 2026-10-16
by: mayusi
source: "kit/lessons/vfx.md"
links: ["[[vfx/index]]"]
project: Parallax
---

Measured in Studio 2026-10-16 (kit/vfx/facts.luau, engine-facts page): an EditableMesh's per-vertex alpha (VfxMesh fadeIn/fadeOut/fadeSides/erode) AND its TextureID/TextureContent alpha are IGNORED - every textured mesh shell draws its whole texture square opaque in the engine while the browser player fades it. Only SurfaceAppearance (ColorMap + AlphaMode Transparency) gives a mesh alpha, and a game script cannot set ColorMap (Plugin capability): author SurfaceAppearances ahead (Rojo/Studio) and clone them. Never judge a mesh layer from the player.
