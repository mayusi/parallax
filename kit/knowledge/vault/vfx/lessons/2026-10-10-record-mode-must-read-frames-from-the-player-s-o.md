---
kind: lesson
area: vfx
date: 2026-10-10
by: mayusi
source: "kit/lessons/vfx.md"
links: ["[[vfx/index]]"]
project: Parallax
---

Record mode must read frames from the player's own render target (readRenderTargetPixels), not canvas.toDataURL: a hidden browser tab's screen buffer stops updating and 40 identical frames poisoned a calibration (tail x1.69). Calibrate only against a booth capture of the SAME preset; a brighter v3 vs an old booth reads x1.9 and means nothing.
