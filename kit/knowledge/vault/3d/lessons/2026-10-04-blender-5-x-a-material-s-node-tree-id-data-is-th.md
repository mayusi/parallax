---
kind: lesson
area: 3d
date: 2026-10-04
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

Blender 5.x: a material's node_tree.id_data is the node tree itself ('Shader Nodetree'), not the material — look materials up by the Material object you iterate, never nt.id_data.name (that bug silently blanked chip/grime/emissive masks on every bake).
