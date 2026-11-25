---
kind: lesson
area: anim
date: 2026-10-10
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

Finished Roblox R6 animations are the only reference the owner's eye accepts; DevForum posts' own .rbxm uploads download without a login (assetdelivery needs one for anything not Roblox-owned). Read them with Lune's @lune/roblox (kit/anim/kfs_dump.luau: KeyframeSequences only, scripts flagged, nothing runs) and import them AS THEY ARE into R6-native clips (kit/anim/kfs_import.py: Pose CFrame -> character space is C0r * T * C0r^T; each Pose's easing runs FROM its keyframe TO the next; a joint missing from a keyframe holds). Folding or retargeting a reference destroys what you came for.
