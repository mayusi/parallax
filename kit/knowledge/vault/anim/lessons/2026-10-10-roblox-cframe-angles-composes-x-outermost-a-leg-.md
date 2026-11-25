---
kind: lesson
area: anim
date: 2026-10-10
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

Roblox CFrame.Angles composes X outermost: a leg keyed frame(h, -yaw, -roll) under a yawed pelvis flexes in the PELVIS plane, so a rotating pelvis swings the planted foot sideways (0.17 studs over a stance). Compose the joint as pelvis^T * R_z(adduct) * R_x(h) (kit/anim/gait.py leg_under) so the thigh flexes in the character sagittal plane.
