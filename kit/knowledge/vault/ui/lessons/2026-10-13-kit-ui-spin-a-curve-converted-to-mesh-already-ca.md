---
kind: lesson
area: ui
date: 2026-10-13
by: mayusi
source: "kit/lessons/ui.md"
links: ["[[ui/index]]"]
project: Parallax
---

kit ui spin: a curve converted to mesh already carries its own UV layer, so an image node with no UV Map node samples THAT one and the whole face reads one colour (the crest was a flat tint until 2026-10-14). Bind the face texture to a named UV Map node. A big flat face toward the key light burns about 1.7x: cards want --exposure -0.8.
