---
kind: lesson
area: kit
date: 2026-11-13
by: mayusi
source: "kit/lessons/kit.md"
links: ["[[kit/index]]"]
project: Parallax
---

The kit's lcg(seed) random generator: its FIRST draw barely moves between neighbouring seeds (seeds 4802 to 4813 all gave a first draw on the same side of 0.5), so a coin flip or a sign taken from the first draw is the same for every nearby seed. Throw two draws away before a yes/no decision, and test a seeded choice over a dozen neighbouring seeds for BOTH outcomes
