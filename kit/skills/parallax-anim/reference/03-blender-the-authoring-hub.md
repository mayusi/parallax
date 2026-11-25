<!-- reference for the parallax-anim route card; verbatim from the skill page (2026-10-16) -->

## Blender (the authoring hub)
- `lune run kit anim rig r15 --blend` → `build/animations/rigs/r15.blend`: one deform bone per Roblox part on the
  engine's pivots, a skinned box body, IK targets + poles for each hand and foot (`ik_RightHand` … on the armature:
  1 = IK, 0 = FK). Built from `kit/anim/rigs/r15.json`; never edit the rig by hand.
- `lune run kit anim blend <Name>` → `assets/animations/<Name>.blend`: the spec's keys on the rig, with the spec's
  easing, markers for the events. Open it in Blender and animate (IK, curves, NLA, add-ons). From then on the .blend
  IS the source: `kit anim <Name>` bakes it first (`kit anim bake <Name>` alone does only that). The .json beside it
  is metadata (priority, loop, feel, beats, gate thresholds; events when the .blend has no markers). Timeline
  markers = events (`Hit`, `Footstep:L`); markers `beat:<name>` span beats.
- The bake samples the evaluated scene (IK, constraints, NLA all count) on the kit's own time grid and converts bone
  matrices to the engine's joint transforms; from a spec it checks EVERY frame against the kit's sampler (bar 6
  degrees: Blender lerps quaternion components where the kit and the engine slerp, a few degrees on a huge swing).
- `lune run kit anim judge <Name>` → `build/judge/anim/<Name>/` (strip.png, motion.png = every frame, PROMPT.md with
  the brief, the measured motion and a 12-principle rubric + three located gaps) for a FRESH reviewer;
  `--record <verdict.json>` validates and keeps the score (/100).
