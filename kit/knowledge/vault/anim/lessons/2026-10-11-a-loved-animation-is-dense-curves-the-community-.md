---
kind: lesson
area: anim
date: 2026-10-11
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

A LOVED ANIMATION IS DENSE CURVES: the community sprint the owner called 'amazing' is keyed every 60th of a second (15-20 keys a limb after curve simplification, 7 on the torso); kit-generated runs used 8 keys a cycle and were rejected. And the kit's import had sampled it at 30 fps, dropping every other frame - the 'legs snap' the owner saw (fixed: native-rate import; snaps.py re-spaces single-frame spikes). Make new animations by EDITING loved curves (kit anim derive: amplify, retime, style, chain, hitstop...) and check movesets as a set (kit/anim/moveset.py), never by filling curves from a few poses.
