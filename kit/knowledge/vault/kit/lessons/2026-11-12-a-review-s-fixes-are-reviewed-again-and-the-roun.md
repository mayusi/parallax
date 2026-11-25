---
kind: lesson
area: kit
date: 2026-11-12
by: mayusi
source: "kit/lessons/kit.md"
links: ["[[kit/index]]"]
project: Parallax
---

A review's fixes are reviewed again, and the rounds have a stop rule. kit review's first review found 15 defects, the review of those fixes found five of them half-fixed plus one serious new one (a yes bound to the preset, not to the pictures), the review of THOSE fixes found three middling ones and nothing serious. So: a round that finds nothing serious closes the cycle - its smaller findings are fixed with tests and not reviewed again; a round that finds something serious is followed by another. And every defect of all three rounds sat in a path no test walked end to end: write the end-to-end test of the path BEFORE the first review, it is cheaper than a round.
