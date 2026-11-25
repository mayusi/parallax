---
kind: lesson
area: world
date: 2026-11-10
by: mayusi
source: "kit/lessons/world.md"
links: ["[[world/index]]"]
project: Parallax
---

kit world look must show the meshes where Roblox puts them: fit the FBX template's OWN imported box (every object of it) to the part's Size, centre it on the CFrame, and undo export_fbx's 180-degree Z pre-turn (Roblox's importer turns the FBX back). The registry's min is the un-turned authoring box: placing by it put every off-centre mesh twice its offset away (SampleRegion's Erdtree root ~152 studs, the Stormwall 24) while the centred trees looked right - so a picture of trees on the ground proved nothing. look_blender.py now reads every placed mesh back against its part's box and fails the run over 0.1 studs (SampleRegion: 1180 meshes to 0.000).
