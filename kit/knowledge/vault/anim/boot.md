---
area: anim
kind: boot
date: 2026-10-18
links: ["[[anim/index]]"]
---

# Animation lane — start here

## Boot line (paste this into any harness to start a Animation session)
You are the Animation lane of this project: R6 animations. Run `lune run kit start anim` first and act on its
`next_action`. Work only on this department; leave every other department's files alone.

## How this lane works
- `kit new anim <Pascal>`, then edit `assets/animations/<Name>.json` (character-space keys; twist `UpperTorso`, never
  `Torso`), or `kit anim blend <Name>` and animate the `.blend` in Blender. Locomotion: `kit anim new Walk --gait walk`.
  A REAL clip (CC0 / CC BY, vetted, in VETLOG): `kit anim import <file> --clip <Clip> --as <Name> [--loop]`.
- R6 attacks: key poses on the owner's rig with its IK legs: `kit anim new <Name> --pose`, then
  `assets/animations/<Name>.pose.json` (check without Blender: `python kit/anim/pose_r6.py --check <file>`);
  `kit anim <Name>` bakes it and saves `build/animations/<Name>.r6.blend`; `kit anim edit <Name>` makes that file the
  source. R6 references: `kit anim import <pack.rbxm> --clip <KeyframeSequence> --as <Name>` (vetted),
  `kit anim measure <Name> --vs <Other>`, `kit anim fit <Name> --to <Reference>`, judged on the owner's rig:
  `kit anim look <Name> --rig R6`.
- POSES FIRST, MOTION AFTER (the owner, 2026-11-13: every method "enforced in the terms of being used"): a strike,
  sword or kick move made after the rule is not made until he said yes to its key poses as they are -
  `kit anim block <Name> --sheet` (the poses held, large, + a real-time gif; about 20 s, builds nothing), his words
  `--note <pose> "<words>"`, his yes `--approve "<words>" --by owner --id <id>`. `kit anim <Name>` and
  `kit anim candidates <Name>` refuse it without that yes, at every build. A STRING of attacks starts one step
  earlier, with its design page: `kit anim design <Set> --new --attacks <n>` (two attacks too alike are named
  cousins before anything is posed; a new move of the set is refused before his yes to the design).
- Check: `kit anim`, then look at the move's SHEET (`build/animations/<Name>.sheet/`: the key poses large, the
  strips, `timing.png` = the timing chart; `kit anim timing <Name>` draws the chart alone) and READ the motion line
  (Hit vs the fastest frame, feet, pops, seam); `kit anim play <Name>` proves it in Studio frame by frame.
- The full recipe: the `parallax-anim` skill (`kit/skills/parallax-anim/SKILL.md`).

## This lane's rules
- The shared rules (originality, safety) are in kit/harness/AGENTS.parallax.md (every client gets them from the MCP server); this lane has no rule of its own yet.
