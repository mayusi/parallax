---
kind: lesson
area: anim
date: 2026-10-11
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

UNDERSTAND A RIG AS EQUATIONS, NOT PICTURES: sweep every control (kit/anim/rig_study.py), write the closed form (kit/anim/r6_rig_model.py), check it on random poses against the rig (kit/anim/rig_model_check.py) until the residual is ~0. On the owner's R6 rig that found three things pictures hid: the head's slide rides the body's turn while its rotation ignores every ancestor; COPY_TRANSFORMS blends WORLD matrices (heads lerped), not deltas; the IK chain's joint swings on a 0.118 circle toward the knee pole by an angle set only by the hip-foot distance. Final residual 0.0003 studs.
