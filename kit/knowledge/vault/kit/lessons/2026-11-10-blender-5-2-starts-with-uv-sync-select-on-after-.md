---
kind: lesson
area: kit
date: 2026-11-10
by: mayusi
source: "kit/lessons/kit.md"
links: ["[[kit/index]]"]
project: Parallax
---

Blender 5.2 starts with UV sync select ON: after picking faces, bpy.ops.uv.select_all(action='SELECT') selects the WHOLE MESH, so the next unwrap or pack runs on every face (the rim's laid strips and stacked copies were unwrapped again over their own UVs, the maps came out 15-40% used). Drive UV operators by the mesh's face selection: set tool_settings.use_uv_select_sync = True, select faces with bmesh (faces.index_update() first: an edit mesh's indices can be stale), select_flush_mode(), never uv.select_all; put the user's setting back after.
