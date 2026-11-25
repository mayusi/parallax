---
kind: lesson
area: anim
date: 2026-10-24
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

STUDIO PROOF of runtime layers (2026-10-22): Motor6D.Transform reads back in single precision - a layer that compares its own last write with == never matches and its offset compounds (30 -> 60 -> 90 deg); compare with a tolerance and give a joint no track drives its clean value back when the layer ends. A background Studio window throttles play to 6-10 Hz: time a playtest off the move's own clock / the first frame after a switch, never wall-clock waits. Another session's rojo serve on the root port syncs ITS game into any place you open - push src/kit into your instance yourself
