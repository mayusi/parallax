<!-- reference for the parallax-anim route card; verbatim from the skill page (2026-10-16) -->

## Rigs (engine data)
`kit/anim/rigs/r6.json` + `r15.json` were read from Studio (`lune run kit anim rig --probe` prints the Luau; run it
through the MCP in Edit mode; `kit anim rig --from <saved json>` ingests it). A custom rig (creature, weapon with
joints): set `TARGET` in the probe to the model's path, ingest, then `"rig": "<Name>"` in a spec. R15 = the newer
AnimationConstraint avatars; every joint frame is axis-aligned, so a character-space rotation IS the joint transform.
One spec drives both humanoid rigs: R6 names map to R15 (Torso→LowerTorso, Right Arm→RightUpperArm…). The R6 version
is a FOLD of the R15 clip (`build/animations/<Name>.r6.clip.json`): Torso = LowerTorso then UpperTorso; an R6 limb
is one piece, so each arm points at the R15 wrist and each leg at the R15 ankle (the thigh and shin summed). A leg
whose R15 foot STANDS (sole within 0.05 of its floor) lands where that foot does, and the R6 pelvis re-grounds to
the standing leg that needs it highest (bent R15 knees would otherwise lift the straight R6 legs off the floor);
a leg in the air that would put its sole through the floor (a straight leg passing under a lowered pelvis) slides
up into the torso by the deficit instead of tilting — its top is hidden inside the torso — and skims 0.08 studs
over the floor. A waist-only twist counter-rotates the R6 legs and moves their hips back so the feet stay planted —
which pins the R6 legs under that clip (R6 has no waist; the compile warns). ONLY the joints you name are
controlled — never list a joint at [0,0,0] "to keep it still": that pins it (an aim pose that lists the legs
freezes walking). Both clips go through the motion gates.
