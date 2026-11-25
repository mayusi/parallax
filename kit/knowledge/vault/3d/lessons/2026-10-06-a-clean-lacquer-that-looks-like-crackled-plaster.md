---
kind: lesson
area: 3d
date: 2026-10-06
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

A clean lacquer that looks like crackled plaster: check the NORMAL map before the colour. The Gjallarhorn's pearl housing had a scan at scan_mix 0.1 but relief at its 1.0 default — full-strength scratch bumps (normal grain median 10.5 deg texel-to-neighbourhood; real curvature only 2.9). Not AO (limiting ao_distance / ao 0.4 barely changed it) and not bevel samples (16 vs 64 identical). Since 2026-10-07 relief defaults to scan_mix; grain fell to 1.6 deg and the housing reads as smooth paint. Measure grain as: angle between each texel's normal and its 7 px average.
