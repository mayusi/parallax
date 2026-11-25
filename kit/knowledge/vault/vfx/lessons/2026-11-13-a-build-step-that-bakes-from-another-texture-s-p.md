---
kind: lesson
area: vfx
date: 2026-11-13
by: mayusi
source: "kit/lessons/vfx.md"
links: ["[[vfx/index]]"]
project: Parallax
---

A build step that bakes FROM another texture's packed sheet must run AFTER the packer: run before it, the dissolve step baked from the source as it was one run earlier and said 'current' (2026-11-13, found by review, not by 28 passing tests - none ran two builds in a row). Test a derived sheet with TWO runs and a source that changes between them
