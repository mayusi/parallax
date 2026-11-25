---
kind: lesson
area: qa
date: 2026-11-12
by: mayusi
source: "kit/lessons/qa.md"
links: ["[[qa/index]]"]
project: Parallax
---

A self-test needle must not be a substring of its fixture's own name: a build's summary prints the piece's name (… kit judge _selftest_texel_bar_need), so expectFlag {texel_bar} could not miss and expectSpared {texel_bar} could not pass. Name a fixture for what it IS (map_need), never for the check it exercises, and assert the needle's presence / absence in the summary by script once.
