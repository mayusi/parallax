<!-- reference for the parallax-vfx route card; verbatim from the skill page (2026-10-16) -->

## Runtime
`local Vfx = require(ReplicatedStorage.kit.Vfx)` — server `Vfx.broadcast(name, where, scale?, target?, { reach = studs }?)` (WHO is sent it: players within a reach of the effect or of its target - the caller's `reach` (`false` or `"all"` = everyone), else the preset's own `"reach"` (studs at scale 1, or `"all"`), else the game's (`Vfx.setReach(studs)`; `Vfx.setReach(false)` = everyone), else the kit's rule: 12 times the effect's own extent at this scale, or as far as one of its layers says it is heard or felt (a sound's `radius`) if that is more, never under 300 studs - over the kit's 110 version 3 files as written that is 300 to 10800 studs, 650 in the middle (a composed preset is counted with its parts, so a play's reach can be more); the 10 older presets 300 to 7200. Only `false` or `"all"` mean everyone: a reach of 0 or a typo is as if none was given. A player with no character is sent it at the event's own send; one who comes INTO reach while the effect still lasts is sent it then, looked for four times a second (one who has just joined is not sent what is already playing until they stand in reach). Every event carries the server's clock, so a client that gets it late starts the effect where its clock would be, or not at all once it is over. Not covered: reach is from the character, not the camera (the server is not told a client's camera); an attach effect that never ends is not kept for those who come later; a version 1 / 2 preset sent late plays from its start; run with ONE client moved about (`kit/selftest/vfx/studio/audience.md`, 2026-11-15: far away it was sent nothing; walking into reach while the effect lasted it arrived 1.34 s late and its first mesh showed 0.15 s after; near it arrived at once; coming into reach after the effect was over, nothing) and with TWO players on a local server (`kit/selftest/vfx/studio/two_players.md`, 2026-11-15, twice: one near and one far - sent to 1, the far one got nothing; moved into reach 1.0 s later it got ONE event 1.4 to 1.6 s late and its first parts showed 0.16 s after, the near one was not sent it again; both near - both; both far - none, and both with `reach = false`). An effect sent to where a RUNNING attacker is (16 studs a second) stands BEHIND them: 4.1 studs on their own screen, 1.0 to 1.2 on the other player's, with no network delay - an effect that must stay on a runner is an attach effect or one on a target part. Unproven: real network delay, more than two players), client
`Vfx.play(...)`; v3 control: `local stage = Vfx.stage(name, cframe, { target = hit, anchors = { blade = part } })`,
`stage:freeze()` / `stage:resume()` (hit-stop), `stage:setTimeScale(0.3)` (slow motion), `stage.time`.
Published games using `mesh` layers: Game Settings -> Security -> "Allow Mesh & Image APIs" (owner ID-verified);
without it those layers skip themselves.

### What the runtime may spend (2026-11-15; the owner's limitations file, F-R01 / F-R02 / F-R04 / F-R06)
- **Detail tiers.** A layer may say `"tier": "Medium"` (the LOWEST detail level it plays at: `Low` | `Medium` |
  `High`; none = it plays at every level, a core layer) and `"tierCount": { "Low": 0.4, "Medium": 0.7 }` (the share
  of its `count` / `rate`, and of its twin's count, a level keeps). The GAME sets the client's level once -
  `Vfx.setDetail("Low")` - and every version 3 effect played after that (a play, a broadcast, an attach, an impact)
  is tiered; one play may say its own (`Vfx.stage(name, cframe, { detail = "High" })`). A layer above the level is
  not built at all (no mesh, no light, no emitter); a cut one emits its share. With no level everything plays as
  written. The validator refuses a tier that is no level and a preset of which NOTHING is left at `Low`.
  **Every effect is tiered, by a rule** (`VfxBudget.auto`): a layer that says no tier of its own gets one from
  what it IS. Never touched: sound, shake, screen, fov, impact, world, lens, highlight, glow, crater, decal, beam,
  trail, and any layer marked `"critical": true`. A sprite, swarm or debris of 6 or more keeps 0.4 of its emission
  at `Low` and 0.7 at `Medium` (of 3 to 5: 0.6 at `Low`). Of the lights that start at one moment the strongest
  (range x brightness) stays, the others play from `Medium`. Meshes go by ELEMENT - the meshes that start at one
  moment, at one place, of one shape, aimed one way: the shells of one thing (a beam's core, body and haze). Of an
  element's shells, ranked by how solid each is (its least transparency), then by life x largest size, the top 0.4
  (one at least) play at every level, down to 0.75 from `Medium`, the rest at `High` only. So a level thins a
  thing's shells and never takes the thing away (the first version of this rule ranked a whole moment by size and
  took heads, cores and one of a pair away whole: its review). An author's own `tier` / `tierCount` always wins and
  never moves another layer. Over the kit's 110 effects: 2600 meshes at `High`, 2521 at `Medium`, 2000 at `Low`;
  particles 45963 / 32457 / 18868. LOOK at a level before trusting it: `lune run kit vfx play <name> --detail Low`
  (the player runs the same rule; a test holds the two to the same layers on every preset). Which shell READS best
  is not in the data - the rule keeps the most solid one; it was looked at on ONE effect, with the first version
  of the rule. An impact preset still may not hold a mesh layer at any tier.
- **The engine's own limit on meshes, measured** (a Studio play client, 2026-11-15). A freshly created EditableMesh
  can still grow, and only **8** of those can be alive at once, whatever their size: the ninth create returns nil
  (the `FixedSize` option of an empty create is ignored). Every kit mesh used to stay growable while it was shown,
  so an effect of a hundred mesh layers drew its first eight. Now a mesh is grown, copied to a fixed-size mesh
  (`CreateEditableMeshAsync(Content.fromObject(mesh), { FixedSize = true })`: same ids, its vertices, UVs and
  colours still move) and the growable one is destroyed at once. ONE mesh is grown at a time (a growing mesh holds
  a large share of the memory; a build waits its turn, a frame or so).
  In the engine (this version, the same play client): built one at a time with no budget, 186 small meshes
  (`rock`) stood before the copy returned nil; one `starblade` held 127 meshes at once, reached 0.6 s after it
  started, none refused; two at once were refused at 132 in use and the client learned 125. So the wall is in
  bytes: about 130 of an ultimate's meshes, more of small ones. A mesh the engine refuses is said as that
  (`the engine gave no place to grow a mesh in`, `the engine's editable-mesh memory is full`) and counted
  (`VfxMesh.stats().engineFull`).
- **The mesh ceiling is on by default.** Every built mesh in use, over all effects, is counted (`VfxMesh.stats()`:
  active, idle, refused, max, reserve, learned, engineFull). The default budget is `{ max = 100, reserve = 10 }` (the engine's wall moved between two sessions on one client: 132 in use, then 114) -
  under the figure above - `max` in use at once, the last `reserve` only for mesh layers and mesh trails marked
  `"critical": true`. And a client LEARNS its own: a device's editable memory is its own and cannot be read, so
  when the engine itself refuses a mesh, the meshes that stand then become that client's ceiling (a later refusal
  with fewer lowers it; of a cut budget a quarter at most is kept for critical cues). The kit cannot tell a full
  memory from a game's own growable meshes holding the places, so a learned ceiling is FORGOTTEN after 30 seconds
  without a refusal, and whenever a budget is set. A game may set its own budget
  (`VfxMesh.setBudget({ max = 60, reserve = 8, perSecond = 6 })`; `perSecond` = fresh builds started a second, off
  by default) or none (`VfxMesh.setBudget(false)`: then only a learned ceiling holds, for its 30 seconds). A build
  over the ceiling is turned away like a failed one and counted, not warned of: a mesh layer then draws its STAND-IN (a plain ball at its size, colour and transparency), a
  mesh trail its flat Trail, a fracture piece a plain block - and a layer turned away is not asked for again. One
  `starblade` at `High` asks for 126: under the default its last meshes wait on the critical share and are turned
  away unless marked (in the engine, with the ceiling then at 120: 108 in use, 2 asks turned away). Counted are meshes, not bytes (a big mesh
  costs more of the engine's memory than a small one); the pool may keep 8 more idle beside those in use. A phone's
  wall was NOT measured.
- **A client's first seconds** (ten cold Studio sessions, 2026-11-16, `kit/selftest/vfx/studio/layers.md`): while the
  player's avatar loads, the engine's `CreateMeshPartAsync` takes 1.15 to 1.65 s a call (0.15 to 0.22 s otherwise,
  in a background client), and the kit builds meshes one after another: one effect of two mesh layers and a life of
  2.6 s, played 2 to 5 s in, showed NO mesh in 8 sessions of 10 - with nothing refused. The engine cannot be made
  quicker, so MESHES ARE MADE BEFORE THE EFFECT, NOT DURING IT:
  `Vfx.prewarmAtSpawn({ "starblade", "getsuga_tensho_v2" }, done?)` - once, from a client script - waits until the
  local player's avatar has loaded (20 s at most), then makes every mesh of those presets into the pool, off any
  effect's clock, and calls `done(cold)` - `cold` names the presets the pool could not hold whole. It RAISES what the
  pool keeps to what every preset warmed so far needs (100 meshes at most, `VfxMesh.KEEP_MOST`: the engine's memory;
  the pool kept 8 in all, so 84 of the kit's 110 effects could never stay warm). `Vfx.isWarm(name)` is CHECKED, not
  remembered: does the pool hold every mesh the preset builds, now (a mesh sequence's frames and a mark draped over
  the ground are built at play and left out). An effect that needs more than 100 kept is never warm, and says so.
  PROVEN on 24 meshes (a stone swarm; ten cold Studio sessions, 2026-11-16): after the warm-up the pool held all 24
  at the play and every stone was a mesh 0.01 s in (5 of 5); played straight away, 5 of 5 were counted and warned of,
  8 of the 24 were meshes as the layer began and all 24 only 2 s later - in one, none before the layer ended.
  WHAT WAS SEEN THEN: a swarm draws a plain block for a stone not built yet, so that session showed the 24 stones
  as blocks (25 parts, 0 meshes) as the layer began; at 2.0 s nothing of the effect was in the workspace. FOUND:
  not a removal - the stage's CLOCK. A step took the Heartbeat's dt, which is the whole previous frame, so an effect
  played inside a long frame (the avatar arriving hitches a client 0.3 to 1.3 s) jumped that far into its life on
  its first step (seen: 1.35 s of the effect gone 0.02 s after the play). The ENGINE's reason: `RunService.Heartbeat`
  hands its listeners the duration of the PREVIOUS frame, not the time since they were made. A step now never moves
  the clock more than the real time since the last (`VfxNet.stepBy`; a spec plays an effect inside a 1 s frame and
  holds its first step to the 0.02 s that really passed): 8 of 8 sessions played during the arrival ran at wall time. A MESH LAYER drew nothing at all until its mesh came (the 2-mesh effect: no mesh in 4 of 5
  early plays). Now a mesh layer draws a STAND-IN - a plain ball at its own size, colour and transparency - until
  its mesh is built, and for its whole life when it never is; `VfxStage.standIns()` counts the layers that showed
  one (a playtest holds a game to 0 once its effects are warmed). An effect never plays invisible: RUN, 15 cold
  sessions of a 2-mesh effect played straight away or as the character arrived - not one blank frame in the layer's
  life; the stand-ins first, the meshes 0.15 to 0.37 s later. EVERY version 3 play on a client of a preset that builds meshes and is not warm is counted:
  `Vfx.coldPlays()` returns (cold, early) - `early` are the plays made before the avatar had loaded or within 3 s
  after it (`Vfx.SPAWN_QUIET`: the engine is still slow then), the ones whose meshes may never show; each preset
  played early is warned of once, by name. PROVEN in Roblox (twenty cold sessions, 2026-11-16): played straight
  away, 5 of 5 were counted and warned of and 4 of the 5 showed no mesh; after the spawn warm-up, 7 of 7 showed
  their first mesh 0.02 to 0.08 s after the play (the second by 0.28 s); not warm but played 5 s after the
  character, 2 of 2 showed theirs at 0.17 s with no warning. A playtest holds a game to it with
  `select(2, Vfx.coldPlays()) == 0`. How many meshes a preset builds is one rule (`VfxBudget.builds`, the same as
  `kit vfx cost`'s built meshes: a test runs the two against each other on every preset).
- **A released stage's mesh trail** takes no new sample; its tail fades and the ribbon goes back to the pool then.
  (A released attach-mode stage itself is not finished by that: something must stop it.)
- **Impacts before the kit has replicated** are not remembered as unplayable: `VfxImpact.ready()` says whether one
  can play now; it is looked for again (half a second apart at most; after a minute that is said once, then every
  ten seconds). The kit is found beside the module, as `ReplicatedStorage.kit`, or as `KitVfx`; it takes presets
  that replicate after it loaded.
- Run in Roblox (a scratch place of the kit's own, a Studio play client, 2026-11-15): the mesh limit and the
  fixed-size copies; the default ceiling (then 120: one `starblade` 108 in use at `High`, 96 at `Medium`, 67 at `Low`, by the tier rule as it is now) and the learned one (107 after two at once that session, forgotten 31 s later);
  that an effect's meshes draw; a preset that arrives AFTER the kit loaded is taken and plays (added on the client -
  and, on a local server with two players, MADE ON THE SERVER after both had joined and broadcast at once: both
  clients had it and played it); a COLD START on both of those clients (an impact asked for on the first frame:
  the kit was not there and it was refused; playable 0.9 to 1.1 s later, and it played); an impact refused while its preset was missing plays once the preset is
  there, in a kit project (`ReplicatedStorage.kit`). Found there and fixed: a preset that is not version 3 was
  "ready" for impacts and none ever played - it is refused and said. Looked at there, the quality level set by hand: Roblox's
  `Glass` material DOES bend the opaque things behind it, from quality level 16 of 21 up (16, 18, 21: stripes
  behind a Glass ball and a Glass pane bend and magnify; 15, 14, 8, 1: plain see-through). (A first look, at an
  unknown level, was read as "does not bend": wrong, and corrected.) So a `haze` shell and a Glass ring bend the
  LIVE scene at high graphics only; below that the baked ring (`kit vfx comp --new shock`) is what shows a bend.
  A fracture's pieces as REAL RIGID BODIES (a debris layer with `"pieces"` and `"floor": "world"`): a slab of 18
  pieces let go piece by piece came to rest on a floor, a step and a ramp, lying over each other. A mark DRAPED
  over uneven ground (a decal layer with `"wrap"`): it lies on a step's top and up a wedge's slope where the flat
  mark shows a sliver; where a cell straddles a vertical wall the sheet stretches down it. Found and fixed there:
  a part's Color does not tint a SurfaceAppearance's picture (the draped mark drew grey) - the appearance's own
  Color does. A layer marked `critical` TAKES THE RESERVE (a made preset of 10 plain mesh layers and 4 critical,
  the budget `{ max = 12, reserve = 4 }`: 12 in use - 8 plain and the 4 critical - 2 plain turned away). A SOURCE
  DESTROYED mid-effect: the part an attached effect rides - its meshes are gone, nothing warned or thrown; a
  stage's anchor part - the effect plays on to its end, nothing warned or thrown. NOT run there, and why: a PHONE
  (none is here; Studio's device emulator changes the screen and the input only - the effect still runs on this
  machine's memory and graphics card - and no script can reach it: what stands in for a phone is the `Low` tier,
  67 of one `starblade`'s 126 meshes, and a ceiling the client learns when its engine refuses a mesh); frame cost
  (the window was in the background: its frame times say nothing); real network delay (a local server has none);
  how a `Low` effect reads beside a `High` one (the scratch place has none of the uploaded textures).
- **The warm-up, after its second review** (2026-11-16): the same preset warmed again (a game that warms on every
  respawn) asks the pool once, not once a respawn; ribbons are one need of them all (two of one size were each served
  by the same kept ribbon), and a play at a scale above 1.5 is cold for them (a ribbon is built at reach x scale);
  `isWarm` and the cold count read the play's detail level (a layer it drops builds nothing); a mesh layer's stand-in
  is outlined as its mesh will be. `VfxMesh.keeps()` says what the pool may keep (100 at most, never lowered).
- **A draped mark's back face, in the engine** (Studio, 2026-11-17): Roblox computes the normals of a two-faced sheet
  from its points - with the back on the SAME points the normals came out as zero vectors and flat axes that ignore the
  slope; with the back on points of its own (as built) the face's point up along the slope and the back's exactly
  opposite. A hit-stop holds the stage's clock (16 frames at 0.75 s seen) and the pieces' rule takes no early stop
  from those steps of 0. SEEN with pieces lying in each other DURING the hold (2026-11-17): a hold at 0.52 s fell
  while 2 pairs lay up to 0.84 studs deep; after it they rested 0.0187 deep at most, as the twin with no hold (0.0184),
  measured on the pieces' real outlines and turns. The stop is taken only when the rule itself says no two pieces lie
  in each other deeper than its skin (`debrisMeet`'s third value), so a step too short to push cannot take it.
