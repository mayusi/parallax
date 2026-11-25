---
kind: lesson
area: vfx
date: 2026-10-24
by: mayusi
source: "kit/lessons/vfx.md"
links: ["[[vfx/index]]"]
project: Parallax
---

Impact frames with draw.semantic on (the default) drop EVERY mesh layer from the energy pass and redraw only aimed tube/cone meshes as wedges (player.js: l.native is any mesh's bounding box): a flame shell / ring / torus at the hit draws NOTHING and the frame shows only the swarms (firewhirl r1-r2: an ember starburst). Frames drawn from a mesh form need draw.semantic false; the frames-need-shapes rule now ignores meshes under semantic frames. Kept as is in the player: loved starblade/nuke frames were judged with it
