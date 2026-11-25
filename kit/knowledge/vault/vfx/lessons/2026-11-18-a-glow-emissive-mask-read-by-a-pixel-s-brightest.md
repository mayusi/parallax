---
kind: lesson
area: vfx
date: 2026-11-18
by: mayusi
source: "kit/lessons/vfx.md"
links: ["[[vfx/index]]"]
project: Parallax
---

A glow (emissive) mask read by a pixel's BRIGHTEST CHANNEL lights a saturated red tail as much as a white-hot core (hk_tongue_gpu, 2026-11-18: the whole flame glowed). Read the light by LUMINANCE times alpha (0.2126 R + 0.7152 G + 0.0722 B): only the yellow-white body passes a 0.6 floor and the cooling cells fade out. Look at the mask beside its sheet at full size before trusting any 'how bright is it' rule.
