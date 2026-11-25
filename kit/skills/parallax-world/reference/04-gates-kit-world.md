<!-- reference for the parallax-world route card; verbatim from the skill page (2026-10-16) -->

## Gates (kit world)
Errors: unknown palette/material, size outside 0–2048, below the kill plane, spawn buried, > 10k parts, a building
too shallow for its stairs, a heightmap source that is not one. Warnings: z-fighting, > 3k parts (mobile), no spawn,
scatter / cover that could not fit. `kit verify` fails if `src/world` drifts from the blueprints.
A part wholly under the land is never emitted (wasted budget). `kit world check` voxelizes a scanned mesh as its OWN
shape (its `build/worldmeshes/<mesh>.mesh.json`, not its bounding box), and on a big map (2-stud cells) walks every
unreachable floor and small trap again at 1-stud cells around it — a narrow stair or doorway the coarse grid misses is
cleared and listed in `stats.fine_rechecked`; anything the fine walk cannot reach stays named.
GROUND CONTACT (blueprint "contact": { "material": "Ground", "max": 600 }): the soft land under every colliding part and
solid mesh whose foot touches it is worn to that material in a ragged skirt of 4-stud cells (env.contact, a flat
integer list the runtime wears after the terrain fills) - nothing meets the grass with a clean seam.
GUIDANCE along the roads (the worn paints): a LANDMARK must be in view from >= landmark_pct (70 %) of the road samples
(landmarks: steps with "landmark": true, or a tree >= 150 studs / a tower >= 60 / a building of 3+ floors / a peak; the
longest blind stretch is named), and PACING: no more than pacing_s (60 s at the player's speed) of road between points
of interest (objectives, landmarks, spawns).
STREAMING + LOD (blueprint "streaming": { "cell": 256, "lod": true }; the game's project sets Workspace StreamingEnabled -
the build's lock reads the project file and stops a world that says "streaming" where it is off):
a step wider than a cell splits into one Model per cell (Name_c<x>_<z>) with LevelOfDetail = StreamingMesh (a far
stand-in), the skyline (backdrop steps) stays one Persistent Model that never streams out.
LOADING INTENT (`kit/lib/worldstream.luau`): cells are cut by place alone; four things they cannot know are words.
"streaming": { "speed": 40, "fall": 300 } - the fastest a player moves (studs a second; 16 on foot, never less)
and the highest drop they take. The build's lock reads the game's project (never writes it) and holds it to:
StreamingMinRadius >= max(64, 4 s x speed) (4 s is the kit's choice; Roblox's page recommends 64 and says more
costs memory - the line says so); StreamingTargetRadius >= twice that; for players faster than a walk,
StreamingIntegrityMode "PauseOutsideLoadedArea" (the engine's own guard); a drop past the minimum radius needs a
named arrival at its landing (WorldStream.ahead(player, name) from the top). Nothing is held where streaming is off.
A step's "stream": "always" (Persistent: never streams out; 400 parts a world at most), "whole" (Atomic: one
piece, never cut into cells; over two cells wide is a warning) or "area". EVERY landmark must say one: a step
typed "landmark": true, the compiler's own (a tree of 150 studs, a tower of 60, a building of three storeys -
"landmark": false says it is none) and a town's landmark house ("landmark": { "stream": "always" }; "stream" on
the town itself is an error). "streaming": { "arrivals": [ { "name", "pos" } ] } names where players are sent:
"pos" is where the feet stand - on a part's own surface (a ramp's slope) or the land, 30 studs over it at most,
with 5.5 studs of room over it. `require(ReplicatedStorage.kit.WorldStream).arrive(player, "Keep gate")` asks
Roblox for the ground (Player:RequestStreamAroundAsync) BEFORE it moves the character; `.ahead` asks only.
Roblox returns nothing on a timeout and promises nothing: a request that took the whole 5 s comes back "late".
