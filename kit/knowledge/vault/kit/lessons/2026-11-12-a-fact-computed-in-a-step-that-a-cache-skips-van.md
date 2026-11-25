---
kind: lesson
area: kit
date: 2026-11-12
by: mayusi
source: "kit/lessons/kit.md"
links: ["[[kit/index]]"]
project: Parallax
---

A fact computed in a step that a cache skips vanishes on the cached run (the packing fact is made during the unwrap; a bake-cache hit skips the unwrap): store it in the cache's own record, and build the fixture TWICE (fresh, then from the cache) before trusting a self-test needle that reads it - the second self-test run would have missed its case.
