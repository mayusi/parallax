---
kind: lesson
area: kit
date: 2026-10-16
by: mayusi
source: "kit/lessons/kit.md"
links: ["[[kit/index]]"]
project: Parallax
---

The python unit tests must run ONE FILE PER INTERPRETER (kit/test/python/run.py): the lanes' modules share names (plan.py, judge.py, trace.py, library.py, find.py, fit.py, measure.py, preview.py, refs.py, silhouette.py, vault.py) and each test puts its lane's folder first on sys.path, so one process imports whichever loaded first. Isolated: 118 files, 1,072 tests, ~15 min on this machine; a crash before unittest's summary counts as one error with the tail printed.
