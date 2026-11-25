---
kind: lesson
area: 3d
date: 2026-10-10
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

A reference MODEL beats found photos for an organic form: kit library get <uid> + kit refs measure <glb> --length-mm <real> gives ONE specimen's orthographic side / front / top traces at real size (found photos are many specimens, in perspective). Trim a sculpt to them (s.from_traces(..., mode='keep', blend=~6 — at 1.5 the cut left flat sliced walls) and a.trace_match(..., bar=0.9); the diff shows what the sculpt lacks (the skull: a too-narrow ramus, the maxilla short of it, the base carved too high): side IoU 0.888 -> 0.922 -> 0.903 softened, front 0.94.
