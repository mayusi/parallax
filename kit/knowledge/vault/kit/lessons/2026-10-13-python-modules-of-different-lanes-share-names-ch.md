---
kind: lesson
area: kit
date: 2026-10-13
by: mayusi
source: "kit/lessons/kit.md"
links: ["[[kit/index]]"]
project: Parallax
---

Python modules of different lanes share names (check.py, library.py, look.py): the combined test run (kit/test/python/run.py) imports whichever loaded first and 8 tests errored in a fresh install. Give new modules unique names (sfxlib, worldcheck, worldlook) or load by path with importlib under a unique name.
