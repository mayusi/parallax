---
kind: lesson
area: anim
date: 2026-10-27
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

ONYX WAS NEVER IN A PREVIEW (2026-10-27): kit/anim/look_r6.py drew only the right weapon (the clip's sword path) - every render of a two-gun clip showed Pearl alone, so the left gun's motion was never looked at before the owner saw it in game. look_r6 now draws the left gun black from grip.left_paths(); and grip._alpha eased sine/quad keys LINEARLY (it called clip.ease, Roblox's pose easing with only Linear/Cubic/Elastic/Bounce) while Blender eased the arm - now Penner curves like Blender. Also: clear <Name>.r6.look before re-rendering, stale frames of an older version mix into sheets and GIFs.
