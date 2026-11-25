---
kind: lesson
area: anim
date: 2026-10-24
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

CUTSCENES IN GAME (2026-10-24): ship the PLAN, not baked poses - a timeline of the kit's own clips (name + start point + length), @idle/@hold spans, the root path, hit-stops and camera keys (kit anim cutscene --timeline -> KitAnimations.Cutscenes) plays on real bodies through src/kit/Cutscene with no gate bent. Proving it: a background Studio's server runs ~8 Hz, so a 67-117 ms hit-stop or a 50 ms teleport gap falls between samples - give the runtime a manual clock (handle.step) and check those at the plan's 60 fps; never count frames after the end (the camera is already handed back)
