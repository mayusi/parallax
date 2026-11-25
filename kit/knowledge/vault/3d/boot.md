---
area: 3d
kind: boot
date: 2026-10-18
links: ["[[3d/index]]"]
---

# 3D models lane — start here

## Boot line (paste this into any harness to start a 3D models session)
You are the 3D models lane of this project: 3D models (weapons, props, vehicles, creatures, building pieces). Run `lune run kit start 3d` first and act on its
`next_action`. Work only on this department; leave every other department's files alone.

## How this lane works
- `kit new asset <snake> [--from sword]`, then ask the owner its brief (`<name>.brief.md`: view, hero features and a
  parts plan, how each part gets made), then follow `kit plan <name>`: ONE planned pass through the stages.
- Gather every reference before any shape, into the asset's PACK (`kit pack <name>`; the build reads it with
  `pk = a.pack()`): a real object's DOSSIER first (`kit dossier new "<object>" --category <kind>`: facts with the
  source's own words, pictures and models checked by script and two reviewers, one blind; the owner approves its
  reference sheet), `kit refs expand / find / dims / patent / coverage`, two reference MODELS (`kit library find /
  get / inspect`, then `kit learn`), `kit trace` every view and part, `kit vision cutout / upscale / albedo`.
- Then `kit study <name> --new`: READ each reference, decide OUR version, answer its matched lessons (locks the shape).
- A generated 3D draft (`kit gen views` / `kit gen` / `kit gen parts`) with the GPU otherwise idle; shape each part by
  its route (CAD from `kit refs profiles`, `kit cad check`, one CAD part alone: `kit cad check <name> --only <Part>`;
  generated parts via `a.import_mesh`; every traced view matched with `a.trace_match`; proportions as `a.param`
  matched by `kit fit`; `kit watch <name> --geo`); surface from data (`rbx.finish` / `rbx.real`, `scan=`, `pattern=`, engraved
  markings, `a.decal`, `a.relief`, `kit gen texture`); mechanism (`a.joint`, `a.disassembly`); look and judge once
  (`kit judge`); `kit showcase` (the game version, `kit optimize`, only when the owner asks).
- Check: `kit plan <name>`; `kit asset <name>`, then LOOK at `build/renders/<name>.png` beside the references.
- The full recipe: the `parallax-3d` skill (`kit/skills/parallax-3d/SKILL.md`).

## This lane's rules
- The shared rules (originality, safety) are in kit/harness/AGENTS.parallax.md (every client gets them from the MCP server); this lane has no rule of its own yet.
