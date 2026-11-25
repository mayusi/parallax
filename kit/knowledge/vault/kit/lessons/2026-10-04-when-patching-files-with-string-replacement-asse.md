---
kind: lesson
area: kit
date: 2026-10-04
by: mayusi
source: "kit/lessons/kit.md"
links: ["[[kit/index]]"]
project: Parallax
---

When patching files with string replacement, ASSERT the old text is present — the formatter reflows long calls, and an unasserted replace silently does nothing (the viewmodel arms kept their old size for a whole test round).
