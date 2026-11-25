---
name: parallax-sfx
description: Make Roblox sound effects (UI clicks, hits, explosions, weapons, abilities, loops) — real recordings layered with synthesis, sound SETS that share one DNA, measured by "ears" and drawn as sound sheets, matched to references the OWNER chose, judged by the owner in a listening booth and in sync with the hit in the engine, played in game as events (Sfx runtime on the Audio API). Use for any sound task or to check a downloaded sound.
---

# parallax-sfx — the route card (the detail is in `reference/`; the record is in `kit/knowledge/vault/sfx/`)

You cannot hear. The pipeline turns sound into evidence you can READ (sheets, numbers against a reference) and
puts the OWNER's ears in the loop early. A score never approves a sound; the owner does.
Start: `lune run kit status --dept sfx`, then `kit help --stage sfx:<stage>`. Reuse first: `kit examples sound`,
`assets/sounds/sets/`, `kit sfx find "<words>"`.

## The clock and the route (the owner, 2026-11-10: "Yes, same budgets" - card b6m2)
- **The clock**: a piece gets 3D's budgets - 10 minutes simple, 30 complex, 60 hero (its spec's `"tier"`, a UI
  screen's `"quality"`; a sound is simple, a sound set complex, unless it says; hero only with `kit approve`). `kit sfx <name>` / `kit sfx set <set>` start it; `kit sfx all` / `kit sfx set` (every one) start any piece new or changed since the last such build.
  A change is a change to what the piece is made of (its spec, the assets it names, a dossier's clip sources) -
  never a look's own output. Past the budget NO CHANGE builds (the piece as it was may still be played, looked
  at, rebuilt): show the owner what there is and its open cards; only his words reopen it: `kit clock sfx
  <name> --extend <minutes> "<his words>"` or `--restart "<his words>"`.
- **The route**: recorded (a real recording in its layers) and/or synth. A piece made a NEW way (a way gained, not one dropped) refuses its build until
  `kit answer sfx <name> --reroute` and every lesson is answered again for the new route (a copied answer
  does not count).

## The rules
1. Real recordings beat synthesis (the synth-only sword set was "middling": booth 6 -> 5, 5 -> 4). Sources: the Roblox
   Creator Store's licensed audio first, then CC0 / royalty-free only (Kenney, Sonniss GDC, Freesound CC0 with the
   owner's key); never Freesound-NC, BBC RemArc, Pixabay; measure-only references indexed `--licence measure-only`,
   matched against, never shipped; every pack vetted + VETLOG with the owner's yes.
2. A sound is never alone: judged in sync with the hit's animation and effect, in the engine (`kit sfx av`).
3. A game has a sonic identity, measured from the owner's references; the set gate enforces it.
4. Seed short noise bursts (an unseeded 90 ms thud swung 8% -> 38% sub between takes); vary takes by pitch / strike /
   round-robin; one loudness per class (± 2 LU); heavier is never quieter or brighter.
5. Direction before sounds (the owner, 2026-10-24): an original place or piece gets `kit sfx direction <Piece> --new`
   - intent, ONE idea, >= 6 references from >= 3 media, 3 pillars, bans, three directions differing on >= 2 axes
   (space / source / density / mood), each a `kit sfx sketch` of the PLACE (beds + events + one convolution space,
   a real IR when vetted); `kit sfx board` plays them to the owner; build to the pick. `kit sfx soundscript` lays the
   places out in journey order (loudness, density, brightness, space). Places can be ALIVE at runtime: kit.WindVoice
   (tonal wind on battlements, cavity physics, follows GlobalWind), kit.GustEvents (rare moments on real gusts),
   kit.EchoZones (places that answer the player's own steps, late) - data in the world's ambience JSON.
6. No two layers mask each other: `kit sfx set` warns when layers hit together in the same loudest bands - carve one
   (a filter) or offset it (the stone hits' thud + sub at 63-79 Hz).

## The route (direction + 9 stages)
| # | Stage | Its gate | Read |
|---|---|---|---|
| 0 | direction | `kit sfx direction <Piece>` ready -> the owner's pick (sketches: `kit sfx sketch <scene.json>`; board: `kit sfx board`) | `kit/direction.py` |
| 1 | refs | up to three reference recordings per class chosen by the OWNER (`kit sfx find "<words>"` for candidates - or by DESCRIPTION: `kit sfx find "<a description>" --describe`, LAION CLAP over the library after `kit vision setup clap-general` + `kit sfx clap index`; `kit sfx clap eval` re-measures it on recorded descriptions - `kit sfx listen <candidates>` for the owner's picks, kept in `assets/sounds/references.json` - `kit sfx plan` reads them) | `reference/01-*` |
| 2 | identity | `kit sfx identity --from refs` (era, saturation, reverb tail, sub weight, brightness band) | `reference/01-*` |
| 3 | design | layers with ROLES (transient / body / sub / mechanical / tail / sweetener / air), `"sample": "lib:<id>"` round-robin, modal / Karplus sources; a SET: shared `dna`, members, `weights`, one `loudness` | `reference/04-*` |
| 4 | match | `kit sfx match <name> --to <ref>`: one difference + ONE edit per role, never a score | `reference/01-*` |
| 5 | sheet | `kit sfx sheet <name> --ref <ref>` LOOKED at (waveform, spectrogram, loudness + brightness over time) | `reference/03-*` |
| 6 | booth | `kit sfx listen <names> [--blind]`: the owner scores 1-10, picks, words -> `kit verdict sound`; the taste profile predicts only AFTER the owner | `reference/01-*` |
| 7 | av | `kit sfx av <name> --video <capture> --at <Hit>`: on its picture; the A/V offset gate | `reference/01-*` |
| 8 | runtime | events in `assets/sounds/_events.json` -> `kit sfx catalog` -> `Sfx.play` / `Sfx.broadcast` proven by a Studio playtest | `reference/01-*` |
| 9 | upload | `kit upload --only assets/sounds/<set>`; `--status` for moderation; grants to the universe | — |

Gates (upload: format, < 20 MB, < 7 min, ≤ 48 kHz, 1-2 ch, not silent, no clipping; sets: every layer does its role
alone, takes differ but stay in the family) and the ears (BS.1770 LUFS, true peak, crest, transient / attack / tail
ms, brightness, flux, onsets, band shares; typical ranges): `reference/02-*`, `reference/03-*`.

## What never worked (`kit/knowledge/vault/sfx/graveyard.md`)
A synth-only sword set · judging a sound alone in the booth.

## Traps
BS.1770 on a 0.5 s sound sits at a block edge (the last block ends at the sound's end; 48 kHz K-weighting) · the booth
server must start outside the Lune job (WMI breakaway) with a per-launch token and Host / Origin checks · private
audio plays only where granted · a Creator Store id can be restricted per experience.

## Read next
`reference/01-the-workflow-*.md` · `reference/04-recipe-essentials.md` · `kit/knowledge/vault/sfx/index.md` ·
`board/plans/archive/2026-10-12-sfx-pipeline-v2.md` · `[[shared/reference-tools]]`.
