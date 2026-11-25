---
kind: lesson
area: sfx
date: 2026-10-25
by: mayusi
source: "kit/lessons/sfx.md"
links: ["[[sfx/index]]"]
project: Parallax
---

A tonal recording can join a tuned synth chord: measure its spectrum peaks first (ffmpeg -> rfft, 5 Hz smoothing), layer only a recording whose strongest peak IS a chord tone, band-limit it round that tone (q ~10) and re-measure the render - the chord tones within ~2 dB of each other and the recording's off-chord peaks >= 15 dB down (Stormhold voice: Sound of Essen 293 Hz = D4; q 6 left a 340 Hz band at -10.8 dB, q 10 -> -16.4)
