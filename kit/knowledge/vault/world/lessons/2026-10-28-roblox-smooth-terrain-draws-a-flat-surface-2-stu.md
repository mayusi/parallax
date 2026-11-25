---
kind: lesson
area: world
date: 2026-10-28
by: mayusi
source: "kit/lessons/world.md"
links: ["[[world/index]]"]
project: Parallax
---

Roblox smooth terrain draws a flat surface 2 studs ABOVE the top of its full voxels (FillBlock 100..104 reads 106; WriteVoxels: surface = partial voxel's bottom + 2 + 4*occupancy). Write heightmaps 2 lower, or a terrain 'ground at 0' covers part floors at 1 (it hid both SampleGame arena floors).
