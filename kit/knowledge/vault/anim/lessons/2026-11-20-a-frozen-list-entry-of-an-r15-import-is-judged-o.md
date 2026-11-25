---
kind: lesson
area: anim
date: 2026-11-20
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

a frozen-list entry of an R15 import is judged on its R6 FOLD (build/animations/<Name>.r6.clip.json, same name): reading the import's own R15 clip says 'not an R6 clip' and looks stale - 5 of the 11 'stale' colliding clips V4 named (McoSwordCombo, MocapSlash1, SwordB, SwordCombo, SwordDashRef) still collide on the fold; check a prune on BOTH files (and an import's foot slide on both: 5 folds passed 0.1 while their R15 clips slid 0.12-0.64)
