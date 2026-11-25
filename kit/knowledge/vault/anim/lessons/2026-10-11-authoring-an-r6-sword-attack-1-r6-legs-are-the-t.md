---
kind: lesson
area: anim
date: 2026-10-11
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

AUTHORING AN R6 SWORD ATTACK: (1) R6 legs are the torso's children - a torso bent 40 deg forward cancels a keyed 45 deg leg swing; key FEET as targets and let the leg solver plant them; (2) R6 reach is 1.58 studs from the shoulder, so a two-hand hilt must stay near the chest - the blade reaches, the hands do not; (3) a slerp of the blade direction from up-back to down-front-left goes round the side: put a breakdown key at the top of the arc; (4) check hand / tip numbers per frame before rendering - a 'blade on the shoulder' stance written in words pointed the blade down-forward.
