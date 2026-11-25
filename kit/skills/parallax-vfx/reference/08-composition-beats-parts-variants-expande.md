<!-- reference for the parallax-vfx route card; verbatim from the skill page (2026-10-16) -->

## Composition (beats / parts / variants) — expanded before anything validates or plays (VfxCompose)
```json
{ "beats": { "strike": 0.0, "release": 2.6, "impact": 2.88 },
  "hits": ["release", "impact"], "hitstop": [{ "at": "release", "hold": 0.09 }],
  "use": [ { "part": "impact_blast", "at": "impact", "as": "impact", "point": "impactGround", "scale": 1,
             "palette": { "gold": "gold", "dust": "dust" }, "mute": ["flood"] } ],
  "variants": { "ice": { "about": "frost", "palette": { "gold": [120, 190, 255] }, "scale": 0.8, "mute": ["beam_*"] } } }
```
- **beats**: any `at` (layers, `hits`, `hitstop`, `use`) may be `"release"`, `"release+0.2"`, `"release-0.1"`.
  Retime a whole effect from one table; a variant may override beats.
- **parts** (`assets/effects/parts/<name>.json`: `palette`, `points`, `beats`, `layers`, `hits`; `kit new vfx <name>
  --part`): a reusable sub-effect. `use` copies it in — layer names `<as>.<name>`, times after the use's `at`, its
  points moved to `point` (a host point or `[x, y, z]`) and scaled by `scale` (sizes, widths, radii, speeds, spans,
  zOffsets too), its colours mapped by `palette` (part colour → host colour name or `[r, g, b]`; unmapped ones join
  the host palette as `<as>.<colour>`), `mute` drops part layers (globs). A part's layers may name host points and
  `"@anchors"` directly (`strike_air` rides `@bladeMid` / `@tip`). Parts validate on their own in `kit vfx`.
  Shipped: `strike_air` (a cut through the air), `impact_blast` (something huge lands), `impact_frames` /
  `impact_frames_void` (a hit's drawn frames; the void one draws a black hole bursting), `attack_call` (the name card),
  and the Starblade round-6 kit (owner: "genuinely your best work", 2026-10-12) — each one a proven showpiece:
  `holy_gather` (field of rising light + pillar + crown, 3.6 s), `fate_circles` (circles CAST round a caster: floor,
  rim ring, standing arc, pillar stack, sky), `circle_barrel` (circles down the line a shot fires through),
  `black_hole` (born where a beam ends, fed, sealed, imploding at 1.0 s — follow with `impact_frames_void`),
  `cataclysm` (flash, fireball mass, dome, shock ring, dust wall, mushroom, rocks; 0 = the burst), `crater_aftermath`
  (glowing fissures, fire, a fire-lit smoke column). Start an ultimate from them: `kit new vfx <name> --from
  fate_ultimate_kit` (the parts alone, recorded and gate-clean) or `--from starblade` (the whole cutscene).
- **An example travels with what it needs**: `kit promote vfx <name>` packs its parts, its textures' specs, the
  finished pictures of imported ones (the download folder never travels) and their uploaded ids into
  `kit/starter/vfx/_deps/<name>/`; `kit new vfx X --from <name>` copies back what the project lacks.
- **variants**: palette / beats / scale / mute / about over the host; `kit vfx play <name> --variant ice`,
  `kit vfx booth <name> --variant ice`, in game `Vfx.play("starblade@ice", ...)` (registered at load; every variant is
  validated by `kit vfx`). Palette swaps and scale presets are variants; the same effect, no copied JSON.
- Prove a refactor onto parts changed nothing: `kit vfx expand <name> [--variant v]` prints the expanded preset
  (what the game / booth / player receive) — diff it against the old one (layer names and point names aside).
