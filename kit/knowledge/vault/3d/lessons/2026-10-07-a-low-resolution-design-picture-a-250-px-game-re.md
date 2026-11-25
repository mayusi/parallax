---
kind: lesson
area: 3d
date: 2026-10-07
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

A low-resolution design picture (a 250 px game render): kit vision upscale --x 4, then kit trace --tolerance 1.0 (the 1.5 px default gave 41 points for a whole pistol). Before measuring it, lay it over the real object's trace with a best-fit offset and length (IoU 0.92 there) — a guessed alignment shifted every part 4 mm.
