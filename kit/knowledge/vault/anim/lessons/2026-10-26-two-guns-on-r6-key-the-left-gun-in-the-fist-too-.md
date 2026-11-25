---
kind: lesson
area: anim
date: 2026-10-26
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

Two guns on R6: key the LEFT gun in the fist too (pose key left_gun {blade, edge} -> grip_left, exported as a Handle pose under the Left Arm) - a gun fixed along the arm can only vary by moving the arm (owner 1/10). Aim from the ROOT: arm clips are torso-relative, so a turned idle/run torso puts every shot ~16 deg off the crosshair unless the arms undo the torso's turn while the guns are up.
