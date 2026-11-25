---
kind: lesson
area: anim
date: 2026-10-24
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

EXPORT OUT OF ROBLOX (2026-10-24): an R6 body is six rigid boxes, so glTF NODE animation (TRS per part, root travel composed in, a sword's blade as its own node, a teleport gap as a STEP scale to 0) carries a clip exactly - no skinning; prove an export by re-importing it elsewhere (Blender's importer and three.js both land every part on the kit's FK to 0.0000 studs). A web page that cannot serve .glb takes the same scene as .gltf JSON with the buffer embedded (kit anim export --gltf)
