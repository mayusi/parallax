---
kind: lesson
area: 3d
date: 2026-10-06
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

The mechanism TRAVEL check never worked: BVHTree.FromObject builds in the object's OWN space, so a group posed through its travel (matrix_world) was tested where it rests, and the >8-colliding-pairs rule could not fire on low-poly parts anyway. A lid swinging through a wall read 'clear'. Trees are now world-space, the depth test runs at five stops along the travel, and after= poses the joints a sequence needs first.
