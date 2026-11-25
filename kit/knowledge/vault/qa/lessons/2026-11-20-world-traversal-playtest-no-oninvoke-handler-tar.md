---
kind: lesson
area: qa
date: 2026-11-20
by: mayusi
source: "kit/lessons/qa.md"
links: ["[[qa/index]]"]
project: Parallax
---

world_traversal playtest: 'No OnInvoke handler / Target is not reachable' on execute_luau to DMN_ID_PLAYSERVER is a stale-window timing issue. The kit's poll for 'Server' in get_studio_state passes but the MCP plugin's OnInvoke handler in that window is not yet registered. Fix: open a fresh Studio window (Start-Process RobloxStudioBeta 'path.rbxlx') and wait ~30 s for it to fully connect before running the playtest. The old window stays stuck even after stop+wait.
