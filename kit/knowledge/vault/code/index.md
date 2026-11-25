# Systems (gameplay code) — the department's page

**The truths:** every game is a folder (`kit game new <Name>` FIRST; `games/.active` is shared — pass `--game`);
server is authority (enabled -> rate limit -> Guard EVERY argument -> Rules -> act; `kit audit` must pass);
`src/shared` is pure; green specs are not a working game — proof means the engine (playtests through the Studio
MCP that fail on any console error); feel is timing (startup / active / recovery, hitstop, latency).

**The route:** brief (GAME.md answered with the owner) -> world (an arena with spawns and objectives) -> systems
(Config + Rules + Service + Controller + spec; hostile cases; `kit fuzz` 0 crashes; `kit mutate` kill rate ≥ 80%)
-> net (remotes from schemas; the red-team playtest) -> moves (frames from the anim's measured phases; the move
sheet) -> playtests (smoke / combat / hud / red-team / perf result files with the console log; the FEEL line) ->
accept (anything the owner rated ≥ 7 is a floor that may not regress).

**Read next:** [[code/graveyard]] · [[shared/studio-mcp]] · [[shared/commits-and-sessions]] ·
`kit/skills/parallax-systems/SKILL.md` · `board/plans/archive/2026-10-12-systems-pipeline-v2.md`.

<!-- kit:auto -->
Lessons: 10 ([[code/lessons|folder]]) · Verdicts: 0 · Golden: 0 · Graveyard: 0 ([[code/graveyard]])
Refreshed 2026-11-24 by `kit vault index`.
<!-- /kit:auto -->
