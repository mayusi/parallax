---
kind: lesson
area: 3d
date: 2026-10-05
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

Blender booleans and merges are NOT reproducible run to run: identical builds emitted 26 of 95 parts in another element order, some with 1-ulp noise, and merge survivors land up to the merge tolerance apart (8 bipod vertices 0.06 mm). Never key a cache on an exact mesh hash, and do not 'canonicalize' by sorting + rebuilding the BMesh (tried: still not exact, AND it broke attachments). Compare geometry with a tolerance (KD-tree, 2x the merge tolerance) and reuse the cached mesh itself.
