# __NAME__ — where everything goes

This folder IS the game: every script, asset, test, note and task for __NAME__ lives here and nowhere else.
Work in it with the kit as usual — while __NAME__ is the active game (`lune run kit game use __NAME__`, or
`--game __NAME__` on any command) every kit command reads and writes inside this folder.

| Folder | What | Made by |
|---|---|---|
| `GAME.md` | the brief: pitch, loop, pillars, places, systems, art + audio direction, decision log | the owner + the model |
| `src/server/` | server Scripts; `<Name>Services/` run by the kit Loader | `kit new game`, `kit new system` |
| `src/client/` | LocalScripts; `<Name>Controllers/` | `kit new game`, `kit new system` |
| `src/shared/` | PURE modules: `<System>Rules`, `<System>Config`, `<Name>Config` (no services, no Instance.new) | `kit new system` |
| `src/net/`, `src/moves/`, `src/world/`, `src/ui/`, `src/animations/`, `src/models/` | GENERATED — never edit | `kit net`, `kit move`, `kit world`, `kit ui`, `kit anim`, `kit asset` |
| `src/kit/` | the kit's runtime, synced from the project (git-ignored) — never edit | `kit game sync` |
| `assets/net/` | remote schemas `<System>.net.json` | you |
| `assets/moves/` | combat moves + sets | you |
| `assets/worlds/` | level blueprints; `terrain/` heightmaps | `kit new world`, `kit world terrain` |
| `assets/sounds/` | sound recipes, sets, `_events.json` | `kit new sound` |
| `assets/effects/` | VFX presets | `kit new vfx` |
| `assets/ui/` | screens + identities + art | `kit new screen` |
| `assets/animations/` | animation specs | `kit new anim` |
| `assets/models/` | 3D build scripts + briefs | `kit new asset` |
| `assets/ids.json`, `assets/uploads.json` | uploaded asset ids, the upload ledger | `kit upload` |
| `tests/` | specs `*.spec.luau`; `playtest/` Studio scenarios | `kit new system`, `kit new playtest` |
| `board/` | this game's tasks, handoffs, journal, decisions | `kit task`, `kit handoff` |
| `docs/` | design notes that outgrow GAME.md (one topic per file) | you |
| `build/` | every generated product (git-ignored) | the kit |

Rojo: `rojo serve games/__NAME__/default.project.json`. Prove it: `lune run kit verify --game __NAME__`.
