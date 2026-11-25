---
kind: lesson
area: world
date: 2026-10-14
by: mayusi
source: "kit/lessons/world.md"
links: ["[[world/index]]"]
project: Parallax
---

kit world shots stalls (1 view in 480 s on an idle GPU) are headless Edge on Windows: msedge hands the page to a child and exits, so killing the launcher leaves the renderer drawing the 3D page forever (GPU contention), and a hidden headless page can stop getting requestAnimationFrame. Fixed in shots.py/web_template: kill by profile dir, timers instead of rAF in ?shots=1. Playwright's Chromium measures the page truth (240 fps) when in doubt.
