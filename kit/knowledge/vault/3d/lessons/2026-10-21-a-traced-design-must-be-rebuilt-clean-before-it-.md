---
kind: lesson
area: 3d
date: 2026-10-21
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

A traced design must be REBUILT clean before it reads as a polished model: a lit render's colour trace carries reflections (holes), grooves (dashes through a band) and pixel wobble — the owner on Scarborough Fair v3: 'the designs on it look so weird ... not a fully polished model'. Clean the mask into the design (kit refs inlays does it by default: holes under 1500 px filled, 15 px grooves bridged, wide regions smoothed hard and thin lines lightly) and build EVERY traced outline with cad_parts.outline (smooth fitted curves, real corners kept), never a raw Polygon; check the fitted face is valid (a fit can cross itself on tiny bumps).
