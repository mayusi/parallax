---
kind: lesson
area: vfx
date: 2026-10-24
by: mayusi
source: "kit/lessons/vfx.md"
links: ["[[vfx/index]]"]
project: Parallax
---

Upload a kit texture AFTER the gate has rebuilt it (lune run kit vfx, then kit upload --only textures/<key>): the uploader sends build/textures/<key>.png - uploading right after regenerating the SOURCE pushed the OLD built image (vortex_skin) and the dry run then said everything was live. A surface: true mesh needs its texture's asset id before the gate's surfaces step passes.
