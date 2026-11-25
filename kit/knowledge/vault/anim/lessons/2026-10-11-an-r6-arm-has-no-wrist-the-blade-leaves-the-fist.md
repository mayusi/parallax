---
kind: lesson
area: anim
date: 2026-10-11
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

AN R6 ARM HAS NO WRIST: the blade leaves the fist at the grip's fixed angle to the arm. Ask for a blade direction AND a hand position and one of them must give: lock the BLADE (it is what reads) and pick the arm on the grip angle's cone nearest the hand (pose_r6.solve_arm). A perpendicular grip (grip_pitch 0, Roblox's tool default) made a greatsword's impact blade 50-60 deg wrong (arms forward, blade sideways); grip_pitch 60 (the blade continues the arms' line) put the hands within 0.2 studs of where an animator would put them at the strike. The arm is 1.58 studs long: a hilt can't sit next to the shoulder - wind-ups behind the head leave the left hand 0.4 short of the hilt.
