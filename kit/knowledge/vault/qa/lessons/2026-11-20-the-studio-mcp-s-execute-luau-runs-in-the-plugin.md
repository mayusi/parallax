---
kind: lesson
area: qa
date: 2026-11-20
by: mayusi
source: "kit/lessons/qa.md"
links: ["[[qa/index]]"]
project: Parallax
---

The Studio MCP's execute_luau runs in the PLUGIN's context with its OWN require cache: a table a test changes in a required module (a Meta entry, a wrapped function) is seen by other kit code required from that same execute_luau, NOT by the game's Scripts / LocalScripts (measured 2026-11-20: a Meta entry set from the MCP on the client never reached AnimRoot's watcher). A proof that needs the game's own scripts to see a fixture (a server-started cue every client plays) is game scripts in a scratch place + StudioTestService:ExecuteMultiplayerTestAsync (tests/playtest/two_players/anim_additive.install.luau).
