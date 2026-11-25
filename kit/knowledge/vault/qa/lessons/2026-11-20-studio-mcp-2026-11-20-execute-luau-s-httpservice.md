---
kind: lesson
area: qa
date: 2026-11-20
by: mayusi
source: "kit/lessons/qa.md"
links: ["[[qa/index]]"]
project: Parallax
---

Studio MCP (2026-11-20): execute_luau's HttpService is now refused for localhost in EVERY datamodel ('domain 127.0.0.1:8765 is not in the Assistant HTTP allowlist'; localhost too, HttpEnabled on or off) - the 11-17/11-18 recipes that served src/kit or a studio_model pack over http.server no longer run. Two ways that still do: patch a module in Edit by plain string replacement on its .Source (find, assert once, sub) for a small fix; or a real Script made in Edit that runs in Play (it uses the engine's own HttpService and DID fetch 127.0.0.1 with HttpEnabled = true - an unsaved scratch place only).
