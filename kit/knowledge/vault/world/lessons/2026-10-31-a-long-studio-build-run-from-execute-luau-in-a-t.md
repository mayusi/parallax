---
kind: lesson
area: world
date: 2026-10-31
by: mayusi
source: "kit/lessons/world.md"
links: ["[[world/index]]"]
project: Parallax
---

A long Studio build run from execute_luau in a task.spawn keeps going after the call returns, so its changes land in whichever later MCP call's undo waypoint ('Assistant N') is open: two Ctrl+Z in Edit silently removed the City of Ruins' last 242 meshes + all 326 parts (2026-10-31). Wrap clear + build in ONE ChangeHistoryService recording and end with ResetWaypoints(), then count every folder against the compile
