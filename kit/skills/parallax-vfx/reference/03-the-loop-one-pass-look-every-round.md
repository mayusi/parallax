<!-- reference for the parallax-vfx route card; verbatim from the skill page (2026-10-16) -->

## The loop (one pass, look every round)
0. `lune run kit lessons vfx` · `lune run kit examples vfx` (proven presets: `starblade` is the v3 reference).
1. **Beat sheet first.** Name the move and its role (basic hit / skill / ultimate). Pick 2-3 reference shots of the
   real thing (anime, games). Write the beats with times (wind-up -> release -> body -> residue), a palette of ~5
   colours, the dominant shape (column / cone / ring / dome), and the size the PLAYER sees: a 40-stud throw is watched
   from ~50 studs, where a 16:9 screen is ~125 studs wide.
2. **Textures from Blender** — `assets/textures/<key>.json` with `"engine": "fx"` and a recipe (below). Reuse the
   library first (`assets/effects/_textures.json`). `lune run kit vfx` renders only what changed (Cycles on the GPU),
   finishes it (glow, white-hot core, alpha, sheet) and registers it. LOOK at `build/textures/_fx_review.png`
   (every texture over black and grey). Then `lune run kit upload --only build/textures/<key>.png` (live in Studio
   within seconds; textures that are not uploaded play as stand-ins).
3. **Preset** — `assets/effects/<name>.json`, `"version": 3`, layers (below). `lune run kit vfx` validates it (the same
   validator the game runs): cut-off layers, unknown textures / points, flipbook vs sheet, particle budget.
4. **Real engine** — `lune run kit vfx booth <name> [--views player,side,hero] [--moments 0.2,1.5,2.6]` writes the run's
   Studio script and prints the steps (the shared capture bridge, no network): `python kit/vfx/capture.py studio ...`
   in the background FIRST, the run's `.studio.luau` through Studio (MCP `execute_luau`, Edit, KitPlaytestScratch),
   then its `.collect.luau`, that answer line saved as `<run>.result.json` for the capture.
   The booth builds a dusk arena with Roblox's own R15 character holding a sword (`@blade`, `@tip`, `@hilt`,
   `@bladeMid` anchors; its raise and chop follow `booth.motion` {raise, swingAt, swingTime}), plays the effect WITH
   its sounds, FREEZES it at every moment and holds it for the capture (which brings Studio to the front first, so
   particles keep up with the clock). Views: `player`, `side`, `hero`, `cine` (a camera PATH: close-up, push-in,
   beside the release, a sweep down the beam, wide on the impact — define your own in `booth.viewDefs` as
   `{ "path": [{ "t", "pos", "look", "fov" }, ...] }`). LOOK at `build/vfx/booth/<name>_all.png`.
   Watch it LIVE afterwards (the booth keeps the effect in the place) from Studio's command bar, Studio in front for
   full frame rate: `require(game.ServerStorage.KitStudioBridge.VfxBooth).replay("hero")` (player | side | hero).
   Videos: dense `--moments` (every 1/24 s) give mp4s; Studio renders ~5 fps when NOT focused, so particles lag the
   clock in those — keep Studio in front while recording.
4b. **Daily loop OUTSIDE Studio** — `lune run kit vfx play <name>` serves the browser player (kit/vfx/player, three.js
   vendored): the preset at full frame rate with the measured Roblox rules, a scrub bar, speed, views (the same
   kit/vfx/views.json cameras as the booth), per-layer mutes and a live brightness graph. `--record --views cine,player`
   renders every frame at 24 fps to `build/vfx/booth/<name>_play_<view>.mp4` + a contact sheet + `<name>_play.metrics.json`
   whose gate says: one intensity peak per declared hit (`preset.hits`), readable at range (>= 3% of the frame),
   <= 4 hues, not blown out. It is a PREVIEW: `python kit/vfx/calibrate.py <name>` compares its brightness curve
   with a booth recording of the same view and says which phase is off; the booth (Studio) stays the truth.
5. Fix what you SEE, re-run 3-4. Judge against the reference shots, never against a gate. Done: `kit promote vfx
   <name>`; learned something: `kit lesson vfx "..."`.
