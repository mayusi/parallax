---
kind: lesson
area: 3d
date: 2026-11-12
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

A constant baked per material is NOT an id map: Cycles blends an island's edge texels, so what a one-number channel holds is the materials' numbers weighted by how much of each texel each material COVERS. To take numbers out of a bake (so they can change without baking), bake each material's coverage (1 where it shows) and compute number x coverage, summed - an id map looked up in a table moved 1% of the final texels (hard edges where the bake had soft ones); the coverage sum is within one level of 255 of the old bake on 0.1% of texels. And a Cycles normal pass is not bit-stable between two fresh bakes (a few texels of a million, one level): hold 'the same maps' to that room, never to the byte across two renders.
