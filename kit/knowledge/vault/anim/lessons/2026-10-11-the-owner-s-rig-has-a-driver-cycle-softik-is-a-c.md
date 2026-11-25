---
kind: lesson
area: anim
date: 2026-10-11
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

THE OWNER'S RIG HAS A DRIVER CYCLE (SoftIK.* is a child of the Leg.*1 bone whose IK influence it drives): evaluate twice per frame (view_layer.update / depsgraph.update) before reading bones, in any tool. Its drivers are simple expressions: they evaluate with --factory-startup / --disable-autoexec. Every bone in that rig is marked deform - a bake must name the part bones (kit_parts on the armature).
