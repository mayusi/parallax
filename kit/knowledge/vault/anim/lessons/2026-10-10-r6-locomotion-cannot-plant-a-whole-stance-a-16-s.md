---
kind: lesson
area: anim
date: 2026-10-10
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

R6 locomotion cannot plant a whole stance: a 16 studs/s run on 2.06-stud straight legs would drop the pelvis 1.1 studs (the fold did this: it read as jumping). Make R6 gaits R6-native (kit/anim/gait_r6.py): pendulum legs of a chosen amplitude whose sole is on the floor and at the ground speed only inside a band around the vertical; the lean and the hip roll lift the pivot a few hundredths, so the stance leg extends by that or the gates' 'feet planted' is vacuous (no contact frames at all at 30 fps).
