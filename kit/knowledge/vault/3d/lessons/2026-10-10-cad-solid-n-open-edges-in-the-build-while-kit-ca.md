---
kind: lesson
area: 3d
date: 2026-10-10
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

'cad_solid: N open edges' IN THE BUILD while kit cad check said 0 = a CAD solid that disagrees with its OWN mesh (the Glock frame: mesh 9.5% under its BRep volume, from an outline KINK where a smoothed strap run joined the trace). cad_run then keeps its finest, needle-strewn mesh and the build's import dissolves the needles into holes. kit cad check now FAILS such a part (volume_untrue) and the build says the cause; bisect the last outline / CAD change by mesh_volume_error (each run ~2 min), never by the open-edge count. Join smoothed runs where the trace is already straight (rbx.profile.smooth_run).
