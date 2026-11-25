---
kind: lesson
area: anim
date: 2026-10-11
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

WHY EVERY R6 ATTACK WAS REJECTED, AND THE FIX: (1) the owner's rig (assets/rigs/R6_IK.blend) has IK legs - Foot.R/L on the floor, the leg pinned at the foot and aimed at the hip, SoftIK.* slider 2 + FK off - and nothing used them: every clip drove FK legs, so a lowered body pushed the legs through the floor or the kit's own leg solver faked it badly. (CORRECTED by measurement: with IK a crouch does NOT splay the legs - they stay vertical and sink into the torso; a wide stance comes from the feet / hip anchors. assets/rigs/R6_IK.md.) (2) The R6 look's cameras stood at -y: the rig faces +y (Roblox -z -> Blender +y; the right arm at +x, a proper rotation), so the owner was shown every attack FROM BEHIND. (3) The bodies were borrowed (punches, mocap) - a greatsword attack must be posed FOR the sword. Fix: kit anim new <Name> --pose -> key poses of the rig's controllers (kit/anim/pose_r6.py), baked off the evaluated rig.
