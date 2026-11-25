---
kind: lesson
area: ui
date: 2026-10-29
by: mayusi
source: "kit/lessons/ui.md"
links: ["[[ui/index]]"]
project: Parallax
---

A shadow catcher on a GLOSSY surface records a dark slab (the object occluding the reflection), and a crop box cuts it square: in game it reads as a weird hard shadow. For sprites over a pre-rendered set, render the object ON the real set and cut by difference against the empty set (alpha = smoothstep(|diff| 3..14), colour = the render, keep the component touching the object). Render full frame: a render border leaves denoiser smear on its edge. Blender resolves a relative output dir against the drive root: pass absolute paths. (SampleGame bench rounds, 2026-10-30)
