---
kind: lesson
area: anim
date: 2026-10-10
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

To keep a finished R6 animator's body and still author the weapon: read the reference into strike.py technique keys (kit anim keys <Name> --from <Ref>): torso pitch/yaw/roll/pos, legs keyed outright (rotation + offset, not foot targets - the foot-target solve was 23-28 degrees off a leaping leg), head look, hilt from the right hand; every frame as a Linear key regenerates the body to 0.2 of the reference, the turning frames to 1.0. Only the arms differ, by design: the weapon arc is the author's.
