---
kind: lesson
area: kit
date: 2026-10-16
by: mayusi
source: "kit/lessons/kit.md"
links: ["[[kit/index]]"]
project: Parallax
---

A test runner built on unittest collects NOTHING from pytest-style files (top-level def test_, no TestCase) and reports 'Ran 0 tests' as green: 12 anim files / 84 tests never ran inside kit verify. Count the tests a gate runs per file; a file with def test_ and a zero count is a hole, not a pass. The runner now routes such files through pytest.
