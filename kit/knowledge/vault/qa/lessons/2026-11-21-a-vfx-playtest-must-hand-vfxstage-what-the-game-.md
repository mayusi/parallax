---
kind: lesson
area: qa
date: 2026-11-21
by: mayusi
source: "kit/lessons/qa.md"
links: ["[[qa/index]]"]
project: Parallax
---

A VFX playtest must hand VfxStage what the game hands it: VfxCompose.expand(preset) first (src/kit/Vfx.luau). vfx_stage_parity's Glass check passed a raw tech = { haze } that VfxStage never reads, so no Glass part was ever made and the check stayed red whatever the haze mapping was; print the measured number, not the table, and prove a check bites by playing the old code once in the scratch window
