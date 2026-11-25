---
kind: lesson
area: kit
date: 2026-10-17
by: mayusi
source: "kit/lessons/kit.md"
links: ["[[kit/index]]"]
project: Parallax
---

A subcommand must never write its department's gate record: kit ui plan/judge/... wrote .verify/ui.json (the build gate), so kit status showed the UI gate red whenever a screen had stages left, and the plan then read its own report instead of the build notes. Per-item work reports under <dept>-<sub>.json (kit status treats a hyphenated name as a report, not a gate).
