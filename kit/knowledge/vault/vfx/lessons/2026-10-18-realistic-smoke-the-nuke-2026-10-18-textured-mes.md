---
kind: lesson
area: vfx
date: 2026-10-18
by: mayusi
source: "kit/lessons/vfx.md"
links: ["[[vfx/index]]"]
project: Parallax
---

Realistic smoke (the nuke, 2026-10-18): textured MESH lobes never read as smoke - hard silhouettes read as bread rolls / potatoes even with our own rendered smoke on them; the visible cloud must be dense volumes of PHOTOREAL flipbooks (the vetted CC0 Unity Labs ul_cloud / ul_explosion / ul_wispy_smoke) in moving bands (staged emitter windows that follow a rising part), with meshes kept for what reads as solid (a glowing fireball core, rope tricks, debris rocks). Our own Mantaflow bakes at resolution 128 / ~90 frames come out as fuzzy pom-poms (no billows) - not good enough as particles. Kit gotchas found: a mesh scale is the unit sphere's RADIUS; a mesh texture needs post border 0 (the default edge fade draws a seam ring); lit (SmoothPlastic) meshes need glow 0 + smooth or the default 0.3 emissive flattens them; a comment placed mid-line in a generator silently drops the keys after it (the fireball's lifetime).
