<!-- reference for the parallax-sfx route card; verbatim from the skill page (2026-10-16) -->

## The workflow (one sound: ~5 min; a set of 8: ~30 min)
1. **Reuse first**: `kit examples sound`, the sets in `assets/sounds/sets/`, the library: `kit sfx find "<words>"`.
2. **A reference**: a real recording of what it should sound like (`kit sfx find`, a file the owner gives). Measure-only
   references (ripped clips) are indexed with `--licence measure-only`: matched against, never shipped.
3. **Design in layers with ROLES**: `transient` (the hit, < 10 ms) · `body` · `sub` (< 120 Hz) · `mechanical` · `tail` ·
   `sweetener` · `air` (> 3 kHz). Real recordings as layers: `"sample": "lib:<id>"` (or a path; a list = round-robin
   per take), `"align": "peak"`. Physical sources: `"modal"` (a struck body: metal / glass / wood, `strike` moves per
   take), `"karplus"` (strings, chains). Shape: `"transient": {"attack": dB, "sustain": dB}`.
4. **A family = a SET**: `assets/sounds/sets/<set>.json` — shared `dna` layers (one sword's ring), members, `weights`
   (light / medium / heavy: heavier = lower, more sub, longer tail), one `loudness` (LUFS). `kit sfx set <set>`.
   **Material matrix**: `"matrix": {"verb": "hit", "base": {...}, "weapons": {...}, "surfaces": {...}}` in the set ->
   a `<weapon>_<verb>_<surface>` member per cell (base + weapon + surface: layers add up, `use` merges, the surface
   last; a member the set already names keeps its own recipe). Each surface gets its own body (metal = the ring,
   wood = a low modal body, stone = grit + a dark thud, flesh = a wet mid layer); no fixed `seed` on the layers that
   should vary per take. Example: `assets/sounds/sets/sword_combat.json` (sword + fist x flesh / metal / stone / wood).
   **A world's ambience**: beds = `"loop": true` members (>= 12 s; `"mod": {"rate", "depth"}` gusts that fit the loop)
   + scatter one-shots in a set; the SEAM gate (no click, level / brightness across the seam) runs on every loop.
   `assets/sounds/ambience/<World>.json` maps kinds -> beds + scatter rules; `kit sfx ambience <World>` derives the
   ZONES from the blueprint (water, forests, stone clusters, open) -> `src/shared/<World>Ambience.json` + the zone map
   `build/sounds/ambience/<World>.png` (LOOK); in game: `kit.Ambience.start(spec)` on the client (beds crossfade by
   where you stand, scatter around you). Example: SampleRegion (`sampleregion_ambience`).
5. **Look**: `kit sfx sheet <name> --ref <ref>` → `build/sounds/sheets/<name>.png` (every take's waveform,
   spectrogram, loudness + brightness over time) and the differences in words ("18 % darker, tail 300 ms longer").
6. **Fit the numbers**: `kit sfx match <name> --to <ref>` (CMA-ES over gains / envelopes / cutoffs / pitch).
7. **On its picture**: `kit sfx av <name> --video build/vfx/booth/<reel>.mp4 --at 0.42 [--cue other@0.8]`.
8. **The owner listens**: `kit sfx listen <names> [--ref <ref>] [--blind]` → a booth on 127.0.0.1:8791 (play takes,
   score 1-10, pick, words → `assets/sounds/<name>.verdict.json`; the taste profile `kit/knowledge/sfx_taste.json`
   learns what the owner rewards once 6+ verdicts exist — read it before designing).
9. **In game**: events in `assets/sounds/_events.json` (switch → blend → takes; bus, priority, voices, cooldown,
   rolloff, duck) → `kit sfx catalog` → `Sfx.play("SwordHit", { at = part, surface = "metal", weight = 0.8 })`
   (client) / `Sfx.broadcast(event, at, params, exceptPlayer)` (server; skip the attacker who already predicted it).
   Upload: `lune run kit upload` (the catalog lists what is not uploaded yet).
