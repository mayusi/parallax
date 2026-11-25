---
kind: lesson
area: 3d
date: 2026-10-10
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

TEXTURE GAPS a code-built model shows (the tree stump, the Glock, 2026-10-10): a material is ONE flat colour unless a scan is mixed in — a.material(vary=) now moves it about its own mean (object-space noise, seamless); a sawn face had no rings — pattern="endgrain" (rings round grain= through the part's centre; 3 mm a year is ~1.5 px at prop distance: 6 mm reads); dust could never show on a dark finish (the dirt constant darkens) — grime_tone="dust". Start every surface from a look (rbx.look, kit materials --looks): base values with their source, scan, pattern, vary, in one line.
