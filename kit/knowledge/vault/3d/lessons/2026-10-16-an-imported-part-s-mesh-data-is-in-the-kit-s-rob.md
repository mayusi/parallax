---
kind: lesson
area: 3d
date: 2026-10-16
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

An imported part's mesh DATA is in the kit's Roblox frame (Y up; the object carries BL_FROM_RBX): any per-face height logic on obj.data must use Y, or go through matrix_world to Blender's Z-up. Reading Z (depth) as up turned the barrel's colour bands into a vertical steel stripe.
