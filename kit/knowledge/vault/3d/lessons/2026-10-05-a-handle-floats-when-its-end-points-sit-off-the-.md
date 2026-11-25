---
kind: lesson
area: 3d
date: 2026-10-05
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

A handle floats when its END POINTS sit off the face, not because they 'only touch': P.handle sinks each end `radius` into whatever face the end points lie on, and the floating check counts any overlap as attached. The old crate's ends were 0.12 studs out (a 0.05 air gap after the inset). Put a_end/b_end exactly ON a real face - a board or a mount plate (mounts also read as how a real handle is fixed). P.handle(segments=6) is round enough for a thin handle (triangles grow with segments: about 3/4 of 8). Text is never made inside a.mirror() - a mirrored word reads backwards: one a.text per face, each with its own facing.
