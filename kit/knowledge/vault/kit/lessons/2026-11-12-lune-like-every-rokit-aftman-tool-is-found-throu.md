---
kind: lesson
area: kit
date: 2026-11-12
by: mayusi
source: "kit/lessons/kit.md"
links: ["[[kit/index]]"]
project: Parallax
---

lune (like every rokit / aftman tool) is found through the PROJECT's tool manifest. Started from a folder outside the project - a made project in a temp folder, as the Python tests use - it fails with 'Failed to find tool lune in any project manifest file' and prints nothing on stdout. A Python tool that calls a Luau helper must start it with cwd = the folder kit/ is in and give it absolute paths (kit/vfx/animatic.py refusals()).
