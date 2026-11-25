---
kind: lesson
area: kit
date: 2026-10-16
by: mayusi
source: "kit/lessons/kit.md"
links: ["[[kit/index]]"]
project: Parallax
---

Parallel sessions in ONE checkout: repo-wide kit verify can only be green at a moment when no session has half-edited Luau on disk (stylua --check runs on every file; the format step fails on another lane's work in progress). Verify your own slices with the lane's commands (stylua + selene on your files, the specs, python tests) and journal milestones only at those moments; a red gate that belongs to another lane is recorded, never fixed from outside it.
