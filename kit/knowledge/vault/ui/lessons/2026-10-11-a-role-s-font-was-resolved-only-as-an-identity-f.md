---
kind: lesson
area: ui
date: 2026-10-11
by: mayusi
source: "kit/lessons/ui.md"
links: ["[[ui/index]]"]
project: Parallax
---

A role's font was resolved only as an identity font KEY (theme[role.font]); a face name in a role ('rankWord': PermanentMarker, 'script': Fondamento) fell back to the body face silently — the character-action rank words and the Arcade5 'Stylish' both shipped in the wrong face until a judge crop showed it. Fixed: theme[role.font] or role.font. When a face looks wrong in a preview, grep the built model's Kit_Font before blaming the font cache.
