---
kind: lesson
area: anim
date: 2026-10-11
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

BVH IMPORT TRAPS (found on the Bandai Namco captures): (1) Blender's BVH importer keys one frame per BVH frame but leaves the scene at 24 fps, so a 30 fps capture sampled by scene time ran 25% slow (402 frames -> 502) - import with update_scene_fps=True; (2) a BVH rest hierarchy is a ZERO pose laid along axes (head tail at z 93, foot tail at z 100), so any height / floor read from rest bones is garbage (height 0.5 -> root travel 44 studs for a half-metre lunge): measure height and floor on the POSED body across the clip. Both fixed in retarget.py; every import's timing before the fix is suspect only for BVH (glTF/FBX carry their own fps).
