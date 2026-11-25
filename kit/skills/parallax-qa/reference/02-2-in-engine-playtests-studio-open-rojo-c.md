<!-- reference for the parallax-qa route card; verbatim from the skill page (2026-10-16) -->

## 2. In-engine playtests (Studio open + Rojo connected + Studio MCP)
1. `lune run kit new playtest <name>` → `tests/playtest/<name>.luau`. First line picks the side:
   `-- runs on: Server` (assert game state, call server code) or `-- runs on: Client` (fire remotes like a real
   player, read the UI). Built-in: `smoke` (player spawns alive, kit runtime present, no instance growth).
2. Write checks with the test API:
   `t.check(name, cond, detail?, fix?)` · `t.wait(s)` · `t.waitFor(fn, timeout?)` · `t.player(timeout?)` · `t.find("A.B.C")`.
   Give every check a `fix` hint — it becomes the next_action when it fails.
3. `lune run kit playtest bundle <name>` and follow the printed steps exactly:
   `start_stop_play(true)` → `execute_luau` (datamodel from step 1, code = the bundle file) → save the returned
   JSON to `build/playtest/<name>.result.json` → `start_stop_play(false)` → `lune run kit playtest record <name> <file>`.
4. While it runs, skim `get_console_output` for errors. Every bundle also measures memory, workspace instances
   and frame time against `qa.perf` in kit.config.json (Studio's memory figure includes the editor).
