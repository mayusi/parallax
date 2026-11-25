---
kind: lesson
area: ui
date: 2026-10-11
by: mayusi
source: "kit/lessons/ui.md"
links: ["[[ui/index]]"]
project: Parallax
---

The preview drew rotation per node only, while the engine turns a rotated frame's children with it: every leaning group (Persona bars, cards) previewed flat. preview.py now composes each node's rotated ancestors into one affine map applied to its drawn box. Two traps on the way: tinting multiplies (a black plate tinted paper stays black — use the white cut piece for a light rim), and TextSize caps at 100 (scale from the clamped size).
