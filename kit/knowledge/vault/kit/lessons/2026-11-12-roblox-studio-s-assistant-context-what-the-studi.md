---
kind: lesson
area: kit
date: 2026-11-12
by: mayusi
source: "kit/lessons/kit.md"
links: ["[[kit/index]]"]
project: Parallax
---

Roblox Studio's Assistant context (what the Studio MCP's execute_luau runs in) cannot call a local server any more: HttpService:GetAsync answers 'HttpService request denied: domain 127.0.0.1:<port> is not in the Assistant HTTP allowlist' for every local port tried on 2026-11-12 (47811, 47812, 47823, by 127.0.0.1 and by localhost), and it cannot read Lighting.Technology ('lacking capability RobloxScript'). So a capture server a Studio script calls back (kit vfx booth, kit ui booth: /grab from HttpService) gets no call. What works: the script signals by what is ON SCREEN and the kit reads the window - kit world studio covers the 3D view with a plain colour from a CoreGui ScreenGui (magenta = start, yellow = next station, cyan = over; CoreGui parenting is allowed) and kit/world/studio_shots.py reads the place's own window with PrintWindow a few times a second, which also tells it where the 3D view is. A second Studio opened on a local .rbxlx (RobloxStudioBeta.exe "<file>") registers with the MCP as its own studio_id within about 30 s.
