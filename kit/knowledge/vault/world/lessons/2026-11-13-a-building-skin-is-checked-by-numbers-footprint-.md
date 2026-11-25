---
kind: lesson
area: world
date: 2026-11-13
by: mayusi
source: "kit/lessons/world.md"
links: ["[[world/index]]"]
project: Parallax
---

A building skin is checked by NUMBERS (footprint, storeys, door size, window run, window sides): nothing in the kit sees WHERE the mesh cut its door. The house mesh counted its bays from the west end of the south wall and the building generator from the east: with an even bay count (a 24-stud front has two) the mesh's door stood in the bay where the building keeps a window - solid stone in front of the walkable gap, a doorway onto an invisible wall. Odd counts hid it for weeks. To see it: one building with a bright glass material and its skin, rendered from the front (kit world look with a view) - a pane inside the mesh's doorway is the fault. The rule now lives in kit/world/housebays.py for both sides; a new mesh kind that takes openings reads it from there.
