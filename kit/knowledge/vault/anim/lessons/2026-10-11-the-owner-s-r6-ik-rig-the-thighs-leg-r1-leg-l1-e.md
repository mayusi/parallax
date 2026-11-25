---
kind: lesson
area: anim
date: 2026-10-11
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

The owner's R6_IK rig: the thighs Leg.R1/Leg.L1 end in a COPY_TRANSFORMS 'IK' whose driver should keep influence 0 in FK, but headless Blender leaves it at 1.0 - every DRIVEN look (imported/folded clips) had its legs pulled to the IK chain, up to 7.7 studs / 115 deg off (the in-place sprint hid it). look_r6 now mutes those copies and FAILS any render whose part meshes are not within 0.02 studs / 1 deg of the clip's FK. Never judge a clip from a render that does not report 'rig = clip within ...'.
