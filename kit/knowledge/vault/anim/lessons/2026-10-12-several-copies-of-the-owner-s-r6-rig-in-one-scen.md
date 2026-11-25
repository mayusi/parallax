---
kind: lesson
area: anim
date: 2026-10-12
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

SEVERAL COPIES OF THE OWNER'S R6 RIG IN ONE SCENE: never obj.copy() the armature - the rig holds its parts with 14 OBJECT-level drivers that a copy drops, and the victim's parts scattered (head 5 studs off) while the per-frame fidelity check still passed (it is relative to frame 0). Re-append the rig from a temp copy of the .blend (bpy.data.libraries.load refuses the open file) and check every copy's parts against the original at REST before driving it (kit/anim/cutscene_r6.py dup_rig).
