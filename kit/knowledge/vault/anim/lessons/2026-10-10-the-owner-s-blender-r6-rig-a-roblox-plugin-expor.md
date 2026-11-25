---
kind: lesson
area: anim
date: 2026-10-10
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

The owner's Blender R6 rig (a Roblox plugin export) is driven, never solved: mute the deform bones' controller constraints, set pose_bone.matrix = delta_from_rest @ bone.matrix_local in hierarchy order with a view_layer.update() between bones (a hand-derived matrix_basis was 1.2 studs off: the rig's bones do not inherit as the textbook formula assumes), keyframe location + quaternion. The meshes are bone-parented (the Torso mesh to the Body controller: re-parent it to the Torso bone keeping matrix_world). One shared material: copy it per part before colouring.
