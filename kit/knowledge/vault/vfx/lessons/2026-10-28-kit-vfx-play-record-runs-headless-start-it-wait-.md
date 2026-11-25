---
kind: lesson
area: vfx
date: 2026-10-28
by: mayusi
source: "kit/lessons/vfx.md"
links: ["[[vfx/index]]"]
project: Parallax
---

kit vfx play --record runs headless: start it, wait for its 'serving' line, then launch the local Playwright Chromium (%LOCALAPPDATA%/ms-playwright/chromium-*/chrome-win/chrome.exe --headless=new --use-angle=d3d11 --window-size=1280,720 <the player URL>) with a FRESH --user-data-dir per run - one shared profile let a still-closing instance swallow every second launch (log: 'served (no recording)'). 12 Sample Game presets recorded this way, no browser pane round trip (vfx-gt 2026-10-28).
