---
kind: lesson
area: kit
date: 2026-11-11
by: mayusi
source: "kit/lessons/kit.md"
links: ["[[kit/index]]"]
project: Parallax
---

A selftest case's needle must be words only the REAL fault prints, never the check's own label or rule id. check_graveyard_rows.py's PASS line read 'graveyard (G9): no graveyard rule', so expectSpared with needle 'G9' always misfired (the full kit selftest stopped there for every lane, 2026-11-11) and expectFlag with 'G9' was hollow (caught with the rule silent). Before registering a case in kit/cmd/qa.luau, run the check on BOTH fixtures and see each needle in the bad summary and absent from the clean one.
