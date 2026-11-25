---
kind: lesson
area: 3d
date: 2026-11-10
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: sample_showcase
---

REVOLVER build 4 (the owner, 2026-11-11, KEEP 'looks amazing', then: the trigger 'doesn't look like it's set properly' and 'is some of the body not fully filled in?'): measured, the two faults were one hole and one slab. (1) The side silhouette against the photo's trace had a 141 mm2 see-through wedge behind the trigger: the photo's frame has a VERTICAL rear edge down to the guard, mine was drawn slanting, and the walnut stopped short of it - a global IoU of 0.936 hid the hole. (2) The trigger's outline matched the photo within 0.5 mm, but it was a 5 mm sheet extruded from it (flat sides, flat face) hanging in that hole: a trigger, hammer or grip is INFLATED (a.pillow) and seated in a slot of solid steel. Draw neighbouring parts from each other's edges (the walnut from the straps' inner edges and the frame's rear edge) so no gap can open; check the side view for HOLES, not only its IoU. And the build ran PROP gates under a hero brief: rbx.Asset defaults to quality='prop' and never reads the brief's tier, so the hero side-trace match and per-part checks never ran - set quality='hero' in a hero's build script.
