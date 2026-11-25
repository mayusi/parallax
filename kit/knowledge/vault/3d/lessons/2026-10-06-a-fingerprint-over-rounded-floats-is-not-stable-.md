---
kind: lesson
area: 3d
date: 2026-10-06
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

A fingerprint over rounded floats is not stable: the part review hashed each part's volume and area to 4 significant digits, and a boolean re-run's noise (~1e-7) flipped the hash whenever a number sat on a rounding edge — the Gjallarhorn's unchanged feathers went back to TODO every other build. rbx_inspect now accepts the answered fingerprint when it is one of the variants the numbers round to within 1e-5 of an edge (_sig_variants; kit/test/python/test_part_fingerprint.py); a real reshape is never one of them.
