---
kind: lesson
area: 3d
date: 2026-10-04
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

Roblox's mesh import turns an FBX 180 degrees about Y and ignores the FBX axis header (verified by uploading the calibration mesh and reading vertices with CreateEditableMeshAsync). The exporters pre-turn geometry; never patch it per asset with Grip rotations.
