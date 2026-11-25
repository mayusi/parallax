---
kind: lesson
area: ui
date: 2026-10-27
by: mayusi
source: "kit/lessons/ui.md"
links: ["[[ui/index]]"]
project: Parallax
---

Cycles shadow-catcher passes leave a faint even alpha over the whole bench: cropping a sprite by alpha grabs the frame, and cropping by the projected box shows as a dark rectangle in game. Crop by the projected box, then multiply alpha by a dilated (31 px) + blurred (9 px) mask of the object's solid pixels (alpha > 200): corner alpha 0, the contact shadow kept.
