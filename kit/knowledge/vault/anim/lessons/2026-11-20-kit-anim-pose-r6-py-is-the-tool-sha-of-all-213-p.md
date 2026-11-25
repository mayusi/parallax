---
kind: lesson
area: anim
date: 2026-11-20
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

kit/anim/pose_r6.py is the tool sha of all 213 pose-route clips (kit/cmd/anim.luau stale check: tool_sha256 = pose_r6.py + clip.py): any edit to it turns kit verify red until every pose clip is re-baked (and Meta.luau rewritten). Land pose_r6 changes as a held patch until the owner schedules the re-bake; data the bake will read later can go in the pose file first (pose_from's sword.lock, 2026-11-20)
