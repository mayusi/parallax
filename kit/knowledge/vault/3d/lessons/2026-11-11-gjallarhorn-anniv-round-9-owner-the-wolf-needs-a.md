---
kind: lesson
area: 3d
date: 2026-11-11
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: sample_showcase
---

gjallarhorn_anniv round 9 (owner: 'the wolf needs a lot of work'): black cracks on an imported generated mesh were not gaps, occlusion or bake seams - they were PATCHES OF FACES WOUND INWARD, made at build time (2,748 edges between faces of opposite winding in the built file, 0 in the generator's GLB): a normal-recalculation pass guesses wrong on a thin shell that crosses itself. Three guesses (a gold core under it, softer AO, a second generation) cost four builds before a 5-second probe of the built .blend (count edges where not e.is_contiguous, render with back faces culled) named it. Fix: rebuild the shell as ONE watertight skin before a.import_mesh (voxel remesh, keep the biggest piece, its own UV atlas) - 0 flipped edges after the build, cracks gone.
