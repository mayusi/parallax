---
kind: lesson
area: vfx
date: 2026-10-24
by: mayusi
source: "kit/lessons/vfx.md"
links: ["[[vfx/index]]"]
project: Parallax
---

Smoke, steam, mist and dust read as COTTON BALLS when built from many generic lit puff cards (gpu_smoke / gpu_dust_puff flung outward): owner 2026-10-24 quenchstrike 'The Effects like Smoke looks horrible', nuke_v2 'the smoke around it could be improved' (308 cards) vs nuke_v4 8.7 (its event simulated). Simulate THE EVENT as one lit flipbook (kit/vfx/gpusim.py: a release + surge for a steam burst, surge-only for a ring rolling out, a cold heavy surge for mist, swirl for a whirl, a short hot release flipped for a falling ring) and play it as ONE sprite standing on the ground (point y = size/2). Traps met 2026-10-25: the sim filling its box reads as a flat-walled block (wider res, edge_fade 0.2+, end the sheet earlier); a low surge moves < 0.0008 a frame at ~2 sim steps a frame (more steps / a wider sheet); a vertically flipped sprite flips its light (light left/right, not top/front). Not a taste rule: calibration - nuke_v2 (8) and gravity_lance (praised) use generic cards
