---
kind: lesson
area: world
date: 2026-10-13
by: mayusi
source: "kit/lessons/world.md"
links: ["[[world/index]]"]
project: Parallax
---

Rojo 7.7 model JSON: a Content property (ParticleEmitter.Texture) must be the IMPLICIT string "rbxasset://..." - the explicit {"Content": ...} form fails the whole build with 'Invalid JSON structure'. Bisect a property with a one-part test project.
