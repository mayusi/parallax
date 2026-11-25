---
kind: lesson
area: vfx
date: 2026-10-27
by: mayusi
source: "kit/lessons/vfx.md"
links: ["[[vfx/index]]"]
project: Parallax
---

kit vfx play --record only PRINTS the player URL and waits (capture.py serve) - nothing records until a browser opens http://127.0.0.1:47811/lib/index.html?name=<preset>&view=<v>&record=1&views=<v>&fps=<n> (the desktop app's built-in browser pane works; open it AFTER the server is up). And a TRAIL layer samples once per recorded frame: a 0.12 s swing at the default 24 fps = 3 samples = a thin bent ribbon; record blade trails with --fps 60 (the game samples every frame).
