---
kind: lesson
area: sfx
date: 2026-10-13
by: mayusi
source: "kit/lessons/sfx.md"
links: ["[[sfx/index]]"]
project: Parallax
---

BS.1770 loudness on SFX: a 0.5 s sound sits right at the 400 ms block edge — decoded from OGG (128 samples shorter) it got 1 block instead of 2 and read 2.5 LU louder. The last block must end at the sound's end. And use the standard's 48 kHz K-weighting coefficients (resample first): a shelf rebuilt from its parameters gave +0.43 dB at 1 kHz instead of +0.69.
