---
kind: lesson
area: kit
date: 2026-10-10
by: mayusi
source: "kit/lessons/kit.md"
links: ["[[kit/index]]"]
project: Parallax
---

Lune's fs reads yield, and Luau forbids yielding inside a metamethod: a lazy __index loader that reads a file returns nil silently (pcall swallows the yield error). Load eagerly at module load instead.
