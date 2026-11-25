---
kind: lesson
area: anim
date: 2026-10-27
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

THIRD-PERSON CHECKS + THE GHOST TEST (2026-10-27): the first-person line-of-fire measure (fp_center_blocked_share, a ray from the head) is meaningless over the shoulder - a dossier names build.tp_camera [right, up, back] (Sample Game 2.2, 0.9, 9) and checks tp_center_blocked_share instead; a family of clips in one dossier scopes checks with "for": [globs]; multi-shot clips use shots_aim_err_max_deg / toss_flight_*_s / shots_while_other_up / shots_from_a_gun_in_the_air. The owner's 'ghost' is measurable: per frame the gun's turn IN THE FIST vs its arm's turn (_scratch/gt/ghost.py); a fresh Opus reviewer found the X's flip at 79 deg in 4 frames with the arm still - fix by moving the hand so the arm carries the turn.
