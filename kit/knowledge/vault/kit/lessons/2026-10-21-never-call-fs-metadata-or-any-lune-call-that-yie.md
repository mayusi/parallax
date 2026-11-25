---
kind: lesson
area: kit
date: 2026-10-21
by: mayusi
source: "kit/lessons/kit.md"
links: ["[[kit/index]]"]
project: Parallax
---

Never call fs.metadata (or any Lune call that yields) inside a table.sort comparator: a comparator cannot yield, so wrapped in pcall every time silently reads as 0 and the sort keeps a random order. Read the times into a table BEFORE sorting (Vault.verdicts / Vault.pairs do).
