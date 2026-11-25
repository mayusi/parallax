---
kind: lesson
area: ui
date: 2026-10-27
by: mayusi
source: "kit/lessons/ui.md"
links: ["[[ui/index]]"]
project: Parallax
---

A glyph-word frame (letters) also holds callers' UIScale pops: every loop over its children (set/fade/tint) must filter to ImageLabel/ImageButton - setting ImageTransparency on a UIScale threw every frame and aborted the render step (GT DamageNumbers), and set() destroying all children silently killed the ammo count's pop.
