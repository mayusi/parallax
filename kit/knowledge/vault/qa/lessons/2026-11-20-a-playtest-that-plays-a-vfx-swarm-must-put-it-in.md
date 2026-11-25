---
kind: lesson
area: qa
date: 2026-11-20
by: mayusi
source: "kit/lessons/qa.md"
links: ["[[qa/index]]"]
project: Parallax
---

A playtest that plays a VFX swarm must put it IN FRONT of the camera: VfxStage leaves a swarm far from the camera where it is (VfxBudget.swarmCulled) - a test effect at (-60, 520, -900) never moved a pellet and its floor.onBounce looked dead (0 bursts); 20 studs ahead of the camera it threw 6 of 6 bursts at the floor.
