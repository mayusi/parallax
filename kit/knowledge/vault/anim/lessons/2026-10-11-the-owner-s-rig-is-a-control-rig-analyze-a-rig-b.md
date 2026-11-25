---
kind: lesson
area: anim
date: 2026-10-11
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

THE OWNER'S RIG IS A CONTROL RIG - analyze a rig before driving it (dump bones, parents, constraints, drivers, the file's own action). assets/rigs/R6_IK.blend: part meshes on deform bones that are CHILD_OF controllers (Body, Head.001, Arm.R/L, FKLeg.R/L under SoftIK FK=True, Main Controller); the owner's action keys only the controllers. kit anim look now keys those and saves build/animations/<Name>.r6.blend with the clip as an action. Muting the constraints and forcing the deform bones gave the same pixels but is not the rig the owner animates with.
