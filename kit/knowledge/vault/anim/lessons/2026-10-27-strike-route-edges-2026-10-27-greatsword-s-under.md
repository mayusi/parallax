---
kind: lesson
area: anim
date: 2026-10-27
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

STRIKE-ROUTE EDGES (2026-10-27, Greatsword's underhip v2): strike.py blade_edges sets the cutting edge at the clip's GLOBAL fastest tip frame, from the tip's sideways motion there. A launcher whose wind-up (a 5-stud blade swung out of a trailing hang) outruns its rise gets its edge from the wind-up: edge_up_at_hit read 0.0-0.4. Fix: give the turn time (the bottom at 0.15 s) and make the rise WHIP the tip (blade down-out at the bottom -> forward-up at the contact), so the rise is fastest and the edge leads up (0.88). A blade kept level at the contact barely moves its tip and loses the peak.
