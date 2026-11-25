---
kind: reference
area: shared
date: 2026-10-16
source: kit/skills/parallax-qa, parallax-vfx (booth), parallax-anim (play), DECISIONS.md #1
links: ["[[qa/index]]", "[[vfx/index]]", "[[anim/index]]", "[[ui/index]]"]
---

# The Roblox Studio MCP — what it can do, and the rules

Disk is the source of truth (`.luau` files, Rojo syncs to Studio); the MCP only RUNS and VERIFIES (DECISIONS #1).
Studio must be open with "Enable Studio as MCP server" on; Rojo connected (`rojo serve <project>`, one project per
port at a time).

What the kit uses it for:
- `start_stop_play(true|false)`, `execute_luau` (a playtest bundle; the result JSON saved to
  `build/playtest/<name>.result.json` then `kit playtest record`), `get_console_output` (any script error fails a
  playtest; read it for toasts and state), `user_keyboard_input` / `user_mouse_input` and `character_navigation`
  (drive a scenario), `inspect_instance` / `search_game_tree` (assert state), `screen_capture` only when a check
  cannot express a pure visual (max one per iteration).
- The booths (VFX, UI) and the UI playtest / v6 proof talk to Studio through the SHARED CAPTURE BRIDGE
  (`kit/tools/studio_capture.py` + `kit/studio/capture_bridge.luau`, card 4s96), never over HTTP: a script run by
  `execute_luau` cannot call a local server ("not in the Assistant HTTP allowlist", 2026-11-12). The command writes
  the run's script (`<run>.studio.luau`, the job inside it; the harness itself is installed ONCE into
  ServerStorage.KitStudioBridge by `<run>.install.luau` when the run answers "install"). The script signals with a
  colour over the 3D view (magenta start, six numbered colours, cyan end) and the capture (`python kit/vfx/capture.py
  studio`, started FIRST) reads the place's own window, brought to the front; the script's answer is the call's
  RETURN value (a long run: `<run>.collect.luau` afterwards), saved as `<run>.result.json` for the capture. Inputs
  the place holds (src/kit, screens, clips) are the PLACE's: a place older than the repo is named in the answer.
  Studio unfocused renders ~5 fps.
- Multiplayer: `StudioTestService.ExecuteMultiplayerTestAsync(playerCount, args)` (plugin security) starts a server +
  N simulated clients; Studio's network simulation gives the lag lab.
- Open Cloud Luau Execution (headless): ~5 task creations / min per key owner, 4 MB return, 450 KB logs, ≤ 10
  unfinished tasks per place; pricing unknown; the owner decides.

Measured engine facts live in each department's lessons (R6 head pitch sign, Beam texture axis, TimeScale 0 still
emits, mesh import turns an FBX 180° about Y, game scripts cannot set SurfaceAppearance maps, ...).
