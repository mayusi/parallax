---
kind: lesson
area: qa
date: 2026-10-17
by: mayusi
source: "kit/lessons/qa.md"
links: ["[[qa/index]]"]
project: Parallax
---

A runner built on unittest reports 'Ran 0 tests' as green for pytest-style files (top-level def test_): 12 anim files / 84 tests never ran in verify until the runner routed them through pytest. Count tests per file; a file with def test_ and zero runs is a hole.
