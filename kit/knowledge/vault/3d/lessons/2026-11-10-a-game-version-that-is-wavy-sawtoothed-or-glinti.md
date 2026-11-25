---
kind: lesson
area: 3d
date: 2026-11-10
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

A game version that is wavy, sawtoothed or glinting up close (the car rim, rework 6ebz, 2026-11-10): render the close-up three ways (as built / normal map unlinked / colour flat) to find which map carries it, count the normal map's texels by tilt, then fix the ROUTE, never the one asset. The causes found, each now in Asset(low=True) and its bake for every game version: the high's normals guessed from long fillet triangles (now the CAD's own B-rep normals); a 1.5 mm round baked into a 1-3 texel/mm map = a 2-5 texel band that stair-steps (now real geometry on the low: rounded() corners over 30 degrees, fillet_mm edges in 3 segments); a near-flat normal map on a low that already matches its high (now flat); the cage short of the widest gap; copies cut into other triangles; a hole's polygon overhanging the high's round hole so rays fell in and hit its wall, a glint (texels tilted past ~72 degrees now take their neighbours' mean); 36-degree thread facets shaded hard (keep a turned detail's facets at 30 degrees or under).
