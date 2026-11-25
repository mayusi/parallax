---
kind: lesson
area: qa
date: 2026-10-28
by: mayusi
source: "kit/lessons/qa.md"
links: ["[[qa/index]]"]
project: Parallax
---

Studio Play driven by MCP while the Studio window is NOT focused runs the client at ~6 fps (Heartbeat dt 0.167 s with nothing playing) and VfxStage clamps its per-frame step, so effect timings sampled by Heartbeat look 'frozen' or late - measure a 1 s idle baseline first, and check an effect's presence the same frame the call returns, not by wall-clock samples (vfx-gt 2026-10-28).
