---
kind: lesson
area: 3d
date: 2026-10-10
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

COLOUR IS CHECKED FROM EVERY TRACED VIEW now (2026-10-10): colour_match compared the model's flat colour map with the reference's lighting-free colour (kit vision albedo) on the side view only; it now takes side, side_left (mirrored), front and back — a.trace_match(<trace>, view=..., albedo=, regions=) per view, facts.colours_by_view. A front picture shows the model's right on its LEFT: the selftest pair colour_front_off / colour_front_ok pins that (a mirrored compare names the correct twin). Top views still wait (their traces lie turned).
