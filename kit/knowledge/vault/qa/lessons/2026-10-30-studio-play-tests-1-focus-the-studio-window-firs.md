---
kind: lesson
area: qa
date: 2026-10-30
by: mayusi
source: "kit/lessons/qa.md"
links: ["[[qa/index]]"]
project: Parallax
---

Studio Play tests: (1) focus the Studio window first - unfocused Play runs ~6 fps AND animation time runs ~2.5x slower than the clock, so any timing or chain-window test lies; (2) never require game modules with side effects (SwordFx, FPSController) from execute_luau in Play - it runs in its own VM and loads a SECOND copy (a duplicate SwordFx prewarmed 5 more EditableMeshes and blew the budget); (3) the MCP click tool manages ~1 click per 0.8 s - drive fast input through a Studio-only BindableEvent hook (e.g. Players.LocalPlayer.SwordTestPress)
