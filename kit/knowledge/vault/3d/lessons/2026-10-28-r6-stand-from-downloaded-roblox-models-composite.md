---
kind: lesson
area: 3d
date: 2026-10-28
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

R6 stand from downloaded Roblox models: composite the best part of SEVERAL checked models (InspWinship AU armour + J-TEC sculpted muscle torso + NotSnicker fists) instead of one base; drape the base's straps/belt onto the new sculpt with a front/back ray-cast offset field; remove coplanar stacked shells (a bigger piece's face lying wholly within 6 mm of a smaller piece = z-fight 'texture bugs', the owner's word) and cut stray loose rods past the limb sides; import every file with size= not height= (a flat disc has no height and is blown up to the Asset size). Script: _scratch/the_world/prep_au4.py
