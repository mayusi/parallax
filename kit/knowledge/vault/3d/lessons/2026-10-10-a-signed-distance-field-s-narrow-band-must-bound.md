---
kind: lesson
area: 3d
date: 2026-10-10
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

A SIGNED DISTANCE FIELD'S NARROW BAND must bound every operation honestly (the sculpt review, 2026-10-10): culling blocks by one Lipschitz 'slope' missed the surface three ways — an ellipsoid's inside bound rises at slope ~779 near its long axis (a limb came out boxy), a hard-edged inflate is a step (no slope at all), and a relief's 'cutoff' measured from its own surface ignored a later inflate (the relief vanished: 11,029 voxels wrong). Now: |d(p) - d(c)| <= slope*|p - c| + margin, where operations that MOVE the surface by a bounded amount (relief 2.5 amp, inflate |amount|, a blend's fillet k/4) add to the margin, and each relief's cutoff carries the slack of everything above it. Test the band against an EXACT field (no cutoff), never against one sharing the shortcut.
