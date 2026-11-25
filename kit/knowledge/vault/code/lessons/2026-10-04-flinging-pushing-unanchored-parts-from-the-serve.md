---
kind: lesson
area: code
date: 2026-10-04
by: mayusi
source: "kit/lessons/code.md"
links: ["[[code/index]]"]
project: sample_game
---

Flinging/pushing unanchored parts from the server: call part:SetNetworkOwner(nil) first — parts near a player are simulated by that client, which silently overwrites a server-set AssemblyLinearVelocity. Hand back with SetNetworkOwnershipAuto later.
