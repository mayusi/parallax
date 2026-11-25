---
kind: lesson
area: ui
date: 2026-10-10
by: mayusi
source: "kit/lessons/ui.md"
links: ["[[ui/index]]"]
project: Parallax
---

A 1:1 replica of a HUD from a picture is traced, not generated: kit ui trace crops the reference at 1:1, upscales x4 (Real-ESRGAN), cuts out (BiRefNet) and, for a gauge plate, blanks the green cells to empty wells and anchors them; kit ui gauge with from_trace lays every piece where the picture has it. Text-prompted emblems scored 40-52 as 'a different design'; the traced gear gauge is the reference's own crest, troughs, caps and pips with live cells. Prompts are for ORIGINAL art; references are for replicas. Two tool traps found on the way: a cap's green glint reads as a 6 px cell (filter < 55 percent of the median width) and the preview drew Fit images as squares (fixed: aspect kept).
