---
area: code
kind: boot
date: 2026-10-18
links: ["[[code/index]]"]
---

# Systems lane — start here

## Boot line (paste this into any harness to start a Systems session)
You are the Systems lane of this project: gameplay systems (games, Rules / Service code, remotes, moves). Run `lune run kit start code` first and act on its
`next_action`. Work only on this department; leave every other department's files alone.

## How this lane works
- A new game: `kit new game <Pascal>` (Loader services, live Configs, data). A system: `kit new system <Pascal>`, then
  edit `<Name>Rules` (pure, tested) and the effect block of `<Name>Service`.
- The kit runtime: `require("../kit/Guard")` from shared code, `ReplicatedStorage.kit.<Module>` from scripts.
- Remotes from a schema: `assets/net/<System>.net.json` then `kit net` (every client argument rate-limited and
  Guard-checked). Combat moves as data: `assets/moves/<Move>.json` plus a set, then `kit move` (frames from the
  animation's measured phases, run by `kit.Moves` on the server).
- Check: `kit verify`; `kit fuzz` (hostile input must not crash) and `kit mutate` (do the specs catch planted bugs?);
  `kit move`, then LOOK at `build/moves/<Set>.png`; a playtest fails on any console error.
- The full recipe: the `parallax-systems` skill (`kit/skills/parallax-systems/SKILL.md`).

## This lane's rules
- The shared rules (originality, safety) are in kit/harness/AGENTS.parallax.md (every client gets them from the MCP server); this lane has no rule of its own yet.
