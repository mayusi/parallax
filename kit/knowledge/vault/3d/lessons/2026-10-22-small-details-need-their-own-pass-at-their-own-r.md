---
kind: lesson
area: 3d
date: 2026-10-22
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

SMALL details need their own pass, at their own resolution: the whole-object trace gives a trigger or a cog hammer a dozen blocky pixels — kit refs detail crops the part, upscales it 4x (Real-ESRGAN), segments it there (colour, a threshold, or SAM 2.1 with --point / --neg clicks: a rose trigger on a rose frame needs negatives) and traces at 1/4 px. And ornate settings are ROUND in section: a jewel's bezel, a gold collar, a medallion = cad_parts.ring(r_in, r_out, h, round=1) (a domed / half-round profile revolved), trim = a bead (round_mm ~0.75 of its height) — the owner on Scarborough Fair: 'the surrounding of it all smooth not a square'.
