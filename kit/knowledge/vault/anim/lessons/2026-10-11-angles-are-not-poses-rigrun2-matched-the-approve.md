---
kind: lesson
area: anim
date: 2026-10-11
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

ANGLES ARE NOT POSES: RigRun2 matched the approved sprint on every angle number (swing amplitudes, opposition phases, bob, asymmetry) and the owner called it genuinely horrible. Flat silhouettes (kit anim sil <Name> --vs <Ref>) showed why in seconds: approved R6 runs carry the legs FORWARD under the leaned body by SLIDING them (0.3-1.3 studs; the swinging leg slides up ~0.5 and forward ~1.0 at passing: the R6 knee) and pump the forward hand ACROSS the midline to chest-head height; RigRun2 rotated rigid legs (splits) and swung the arms straight fore-aft (airplane arms). Build locomotion from measured key poses (kit anim new <Name> --cycle run, kit/anim/cycle_r6.py), check SHAPE (kit anim profile: forward hand from midline / height, front-foot reach, heel kick), and look at silhouettes before textured renders.
