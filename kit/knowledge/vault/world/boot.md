---
area: world
kind: boot
date: 2026-10-18
links: ["[[world/index]]"]
---

# World lane — start here

## Boot line (paste this into any harness to start a World session)
You are the World lane of this project: levels and maps (worlds, terrain, world checks). Run `lune run kit start world` first and act on its
`next_action`. Work only on this department; leave every other department's files alone.

## How this lane works
- `kit new world <Pascal> [--from BattlegroundsArena]`, then edit `assets/worlds/<Name>.json` (generators: room,
  building with stairs, cover, path, breakable ...; terrain: `kit world terrain <Name>`, then a `heightmap` op).
- Check: `kit world check <Name>` (R6 reachability, traps, spawn fairness, camera, knockback room), then LOOK at
  `build/worlds/checks/<Name>.png`; `kit world look <Name>` for eye-level views; `kit world`.
- The full recipe: the `parallax-world` skill (`kit/skills/parallax-world/SKILL.md`).

## This lane's rules
- The shared rules (originality, safety) are in kit/harness/AGENTS.parallax.md (every client gets them from the MCP server); this lane has no rule of its own yet.
