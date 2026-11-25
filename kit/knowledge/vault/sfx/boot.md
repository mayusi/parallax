---
area: sfx
kind: boot
date: 2026-10-18
links: ["[[sfx/index]]"]
---

# Sound lane — start here

## Boot line (paste this into any harness to start a Sound session)
You are the Sound lane of this project: sounds (sound specs, sets, the listening booth). Run `lune run kit start sfx` first and act on its
`next_action`. Work only on this department; leave every other department's files alone.

## How this lane works
- `kit new sound <snake>`, then edit `assets/sounds/<name>.json` (layers with roles; real recordings:
  `kit sfx find "<words>"`, then `"sample": "lib:<id>"`). A family: `assets/sounds/sets/<set>.json` (shared DNA,
  light / medium / heavy), then `kit sfx set <set>`. Fit to a reference: `kit sfx match <name> --to <ref>`. In game:
  events in `assets/sounds/_events.json`, then `Sfx.play` / `Sfx.broadcast`.
- Check: `kit sfx sheet <name> --ref <ref>`, then LOOK at `build/sounds/sheets/<name>.png`; the OWNER listens:
  `kit sfx listen <names>`; on its picture: `kit sfx av <name> --video <reel>`; `kit sfx catalog`.
- The full recipe: the `parallax-sfx` skill (`kit/skills/parallax-sfx/SKILL.md`).

## This lane's rules
- The shared rules (originality, safety) are in kit/harness/AGENTS.parallax.md (every client gets them from the MCP server); this lane has no rule of its own yet.
