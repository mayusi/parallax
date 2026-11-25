---
kind: lesson
area: world
date: 2026-11-18
by: mayusi
source: "kit/lessons/world.md"
links: ["[[world/index]]"]
project: Parallax
---

Every *.json directly in assets/worlds is read as a world blueprint - by kit world (it compiles each) and by the lane locks (LaneLocks pieces). A world's side file (its bible, a plan) goes in a subfolder (assets/worlds/bible/<Name>.json), never <Name>.bible.json beside it; build/worlds/ holds compiled worlds and nothing lists it, so a scratch copy for a render (<Name>.corner.json) may sit there - the look renderer finds the world's meshes from the file's own folder, so a copy elsewhere renders every mesh as missing.
