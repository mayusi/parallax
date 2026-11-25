---
kind: lesson
area: world
date: 2026-10-28
by: mayusi
source: "kit/lessons/world.md"
links: ["[[world/index]]"]
project: Parallax
---

Pushing big build data into a place that has HTTP off and no kit runtime: carry it in through Rojo as StringValue chunks (180k chars) + the builder as a ModuleScript inside a synced model.json, run phases one MCP call each (a 250-high terrain clear over 10 km times the call out but finishes), then sync the clean model back.
