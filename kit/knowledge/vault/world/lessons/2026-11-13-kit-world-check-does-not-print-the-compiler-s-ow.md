---
kind: lesson
area: world
date: 2026-11-13
by: mayusi
source: "kit/lessons/world.md"
links: ["[[world/index]]"]
project: Parallax
---

kit world check does not print the compiler's own warnings (z-fighting, part budget): a generated town passed it with 0 errors while World.compile warned of 240 faces in one plane. That warning also cries wolf on every building of two floors (a slab edge inside a wall, a lintel top under the floor above) and skips every part that is not axis-aligned (a wall run toward -X is one). So a generator's test reads World.compile's issues itself and compares the count with the same houses stood 1,000 studs apart in one compile: what the generator ADDS is the difference.
