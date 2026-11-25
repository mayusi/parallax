---
kind: lesson
area: kit
date: 2026-11-12
by: mayusi
source: "kit/lessons/kit.md"
links: ["[[kit/index]]"]
project: Parallax
---

A guard that says 'this path must not be that file' cannot be written as a comparison of spellings: one file has many (./x, X, the absolute path, and on Windows a trailing dot or space, an 8.3 short name, a ::$DATA stream). Say where the path MUST be instead (a test fixture's locks file: a plainly spelled file under build/) and refuse everything else (Locks.useFixture).
