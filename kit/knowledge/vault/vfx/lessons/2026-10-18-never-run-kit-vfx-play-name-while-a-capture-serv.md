---
kind: lesson
area: vfx
date: 2026-10-18
by: mayusi
source: "kit/lessons/vfx.md"
links: ["[[vfx/index]]"]
project: Parallax
---

Never run 'kit vfx play <name>' while a capture server (capture.py serve) is serving the same preset: the server's hot-reload rewrites build/vfx/play/<name>.json while play writes it and the bundle JSON comes out corrupt (page: 'kitPlayer is not a function', console: Unterminated number in JSON). Stop the server, rebuild, then serve.
