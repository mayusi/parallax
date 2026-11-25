---
kind: lesson
area: 3d
date: 2026-11-12
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

Sharp enough is one texel a screen pixel where the piece is judged: 1028 px a metre for a hero piece at 0.75 m, 257 for a prop at 3 m (rbx_optimize.texel_bar). Measured 2026-11-12 on 96 built models: the main mesh's median is 510, 76 of 89 under 1028, and the faces cover a median 0.50 of their map. A hero master without tex= is now sized by its surface (4096 from two square metres up); read texel_bar and facts.texel_bar after every build; never name tex= on a hero master unless you mean it. Game maps stay 1024 until one test upload was looked at (reference/14).
