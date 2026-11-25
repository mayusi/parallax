---
kind: lesson
area: 3d
date: 2026-11-10
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

A COUPLED MECHANISM (the revolver, 2026-11-10): a.joint checks each joint ALONE, so a cylinder turning while its stop is still up in the notch passes; a.cycle poses every joint together frame by frame (gate mechanism_cycle) and keys the action on the .blend's timeline for the owner. Each joint eases between ITS OWN keys - HOLD a joint with an extra key wherever it must stay put (a pin keyed at frames 1 and 26 sinks the whole time between: the first 'timed' fixture collided for exactly that). Two low-poly boxes passing through each other never reach the 8 colliding triangle pairs: the cycle check also runs the surface-depth test. Real mechanisms need their real cuts: the channel a hammer's tail swings into inside the grip frame, the frame's groove an ejector rod strokes through.
