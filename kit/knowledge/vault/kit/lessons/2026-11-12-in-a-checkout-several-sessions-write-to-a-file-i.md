---
kind: lesson
area: kit
date: 2026-11-12
by: mayusi
source: "kit/lessons/kit.md"
links: ["[[kit/index]]"]
project: Parallax
---

In a checkout several sessions write to, a file is looked at AT the commit, not minutes before: f494f468 added kit/cmd/qa.luau whole a moment after another session had put ten lines of its own there, and kit selftest crashed on the committed tree (a call to a function that session had not committed). The dry run's line count said 29 where I expected 19 and I did not read it. So: for every modified file print its hunk count in the dry run and READ it; stage a file another session may touch through its own hunks (git apply --cached of a filtered patch), never whole; and commit only the tree the dry run showed (write the tree's hash down in the check, compare in the commit). And run the gate self-test on the committed tree after every kit commit: this was found only there.
