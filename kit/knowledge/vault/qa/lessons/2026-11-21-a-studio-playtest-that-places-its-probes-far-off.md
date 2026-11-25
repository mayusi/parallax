---
kind: lesson
area: qa
date: 2026-11-21
by: mayusi
source: "kit/lessons/qa.md"
links: ["[[qa/index]]"]
project: Parallax
---

A Studio playtest that places its probes far off (base 800 studs away) silently skips anything the kit culls by camera distance (a swarm past VfxBudget.SWARM_CULL never updates, so its cost read -1): put the camera near the probe and restore it after. A check of the form 'n == 0 or all good' passes on nothing - require n > 0. The kit home's own project must map src/kit/server like every kit game (it did not: VfxDebris group never registered, 0 of 8). A background Studio window draws ~6 fps: front it (_artifacts/studio_x/front.ps1) before timing checks.
