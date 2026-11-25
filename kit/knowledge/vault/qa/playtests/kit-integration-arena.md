---
kind: playtest
area: qa
name: kit_integration_arena
status: fail
date: 2026-11-21
links: ["[[qa/index]]"]
---

# Playtest kit_integration_arena: FAIL (63/68 checks, 2026-11-21)

- What failed in the last run:
  - [attacker client] this client's copy of the attacker plays each hit's contract clip (the server's track id): 5/5, loaded here 0/5 ({"Katana3":{"move":"Katana3","ui":1795228730.413798,"flash":179522873
  - [attacker client] Stats.DataReceiveKbps NOT MEASURED: it read 0.0 in all 38 samples of the fight (Studio's local test)
  - [victim client] this client's copy of the attacker plays each hit's contract clip (the server's track id): 5/5, loaded here 0/5 ({"Katana3":{"move":"Katana3","ui":1795228730.412026,"flash":1795228730.
  - [victim client] Stats.DataReceiveKbps NOT MEASURED: it read 0.0 in all 29 samples of the fight (Studio's local test)
  - both clients saw each hit within one frame of each other: worst 24.9 ms <= 16.7 ms (latest after the server's contact 44.0 ms; A throttled false, B throttled true) (Katana1: A +44.0 ms B +36.7 ms; Kat
- Runs (newest first; kit playtest run kit_integration_arena):
  - 2026-11-21 FAIL 63/68 · 30 MB · 0.2 ms/frame
