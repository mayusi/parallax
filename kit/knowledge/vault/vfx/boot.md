---
area: vfx
kind: boot
date: 2026-10-18
links: ["[[vfx/index]]"]
---

# VFX lane — start here

## Boot line (paste this into any harness to start a VFX session)
You are the VFX lane of this project: effects (VFX presets, textures, meshes, the player). Run `lune run kit start vfx` first and act on its
`next_action`. Work only on this department; leave every other department's files alone.

## How this lane works
- `kit new vfx <snake> [--from hit_sparks]`, then edit `assets/effects/<name>.json`.
- Check: `kit vfx <name>`, then look at `build/vfx/<name>.png` (frames over time). Make and judge the effect ALONE in
  the browser player (`kit vfx play <name>`), not in Studio.
- The full recipe: the `parallax-vfx` skill (`kit/skills/parallax-vfx/SKILL.md`).

## This lane's rules
- **The method plan (owner, 2026-11-13, a MUST).** His 104 VFX methods are the kit's register (`kit vfx methods`).
  Before a chart is shown to him every beat says which of them it is made with (`kit vfx methods --set <set>`);
  `kit vfx` refuses a piece off its plan. The skill's `reference/18-*` has the rules.
- **The VFX library rule (owner, 2026-10-12, a MUST).** Everything the VFX pipeline makes is saved, packaged by part
  and named properly, in `library/vfx/` (every effect with its source, the expanded version that plays, its previews
  and recordings, the owner's verdicts and EVERY earlier version; every part, texture (spec AND finished sheet) and
  mesh, each with a README saying what it is and who uses it; nothing is ever deleted). `kit vfx` and
  `kit vfx play --record` save it for you; `kit verify` FAILS when anything made is missing or stale
  (`lune run kit vfx vault` fixes it). Owner verdicts: `kit vfx vault verdict <effect> "<words>" [--score N]`. Reuse
  before making: `kit vfx vault find "<words>"`, `kit vfx vault get <effect> --as <new>`, the parts in
  `assets/effects/parts/` (`"use": [{"part": ...}]`), `kit new vfx <name> --from fate_ultimate_kit`.
