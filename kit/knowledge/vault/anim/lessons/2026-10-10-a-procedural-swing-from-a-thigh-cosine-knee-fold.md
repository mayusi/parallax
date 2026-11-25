---
kind: lesson
area: anim
date: 2026-10-10
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

A procedural swing from a thigh cosine + knee fold scuffs the floor 2-3 frames before the plant: the stance knee and the pelvis roll lower the swing hip while a knee folded less than twice the thigh's forward angle (the shin swings toward vertical) reaches further down than a straight leg. Never clamp it per frame (the knee snaps where the lift starts or stops): size ONE smooth bump over the whole cycle in a pre-pass (kit/anim/gait.py: bump*sin(pi*u), every in-air frame >= CLEAR under the pelvis as it stands that frame) and apply it by swinging a forward-reaching leg a little further (knee as planned) or folding the knee of a leg under the hip (IK at the same ankle lead), blended by the ankle's lead (THIGH_LIFT_X). A pure IK ankle path (apex under the hip) folds a run knee 136 deg with the thigh horizontal: keep the proven pose shape as the target and only lift it.
