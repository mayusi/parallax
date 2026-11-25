---
name: parallax-systems
description: Build Roblox gameplay code and its infrastructure — the game skeleton (Loader services, live Configs, data), server-authoritative systems with pure tested rules, remotes generated from schemas, combat MOVES AS DATA (frame data from the animation, a server hit loop), and proof that means it (fuzzing, mutation testing, playtests driven in Studio that fail on any console error). Use for any scripting: abilities, combat, inventory, shops, data, NPCs, rounds.
---

# parallax-systems — the route card (the detail is in `reference/`; the record is in `kit/knowledge/vault/code/`)

Start: `lune run kit status --dept code`, then `kit help --stage code:<stage>`. Green specs are not a working game:
proof means the engine. Plan + idea bank: `board/plans/archive/2026-10-12-systems-pipeline-v2.md`.

## The rules
1. Every game is a folder: `lune run kit game new <Pascal>` FIRST (GAME.md's questions asked of the owner;
   `src/`, `assets/`, `tests/`, its own `board/`, a Rojo project, a synced kit runtime); `kit new system` refuses
   without a game; `kit verify` fails on new gameplay code at the root; `games/.active` is shared — pass `--game`.
2. Server is authority: enabled -> `limit:take(player.UserId, os.clock())` -> `Guard.*` on EVERY client argument ->
   `Rules.check(...)` -> act -> reply; a malformed packet returns silently; never trust client positions, damage,
   prices or ownership. `kit audit` enforces it and fails the build otherwise.
3. `src/shared` is pure (no `game:GetService`, no `Instance.new`; siblings via `require("./X")`); strict mode;
   stylua + selene clean; `task.wait/delay/spawn`; per-player tables cleared on `PlayerRemoving`.
4. Feel is timing: startup / active / recovery frames from the anim's measured phases, hitstop, latency — measure it.
5. Libraries only via `lune run kit add` (profilestore, trove, cmdr, zap) or vetted + VETLOG.

## The route (7 stages)
| # | Stage | Its gate | Read |
|---|---|---|---|
| 1 | brief | `kit game new <Name>`; GAME.md answered with the owner; `kit game check` | `reference/01-*`, `02-*` |
| 2 | world | an arena from the world generators with spawns + objectives; `kit world check` 0 errors | parallax-world |
| 3 | systems | `kit new system <Pascal>` -> Config + Rules (pure) + Service + Controller + spec; every DECISION in Rules + a spec case (hostile input too); `kit fuzz` 0 crashes; `kit mutate` kill rate ≥ 80% | `reference/03-*`; an engine API in doubt: `kit docs <words | Class.member>` (Studio's own reference with the declared type) |
| 4 | net | `assets/net/<System>.net.json` -> `kit net` -> `src/net/<System>Net.luau` (rate-limited, Guard-checked wrappers; unbounded numbers / strings / vectors refused); `kit audit` green; a red-team playtest | `reference/05-*` |
| 5 | moves | `assets/moves/<Move>.json` (+ sets) -> `kit move`: frames `from_anim`, hitboxes per frame, cancels, on-block advantage, TTK, the move sheet LOOKED at; `Moves.serve` on the server | `reference/04-*` |
| 6 | playtests | `kit new playtest <snake>` -> `kit playtest bundle` / `run` through the Studio MCP; any console error fails; result files with the console log; the FEEL line | parallax-qa |
| 7 | accept | `kit verify --game <Name>` green; anything the owner rated ≥ 7 accepted as a floor; `kit verdict system` | — |

The kit runtime (`ReplicatedStorage.kit`, kit-owned — never edit): Guard · RateLimit · Loader · Configs · Moves /
MovesRules · Sfx / SfxRules · Vfx · Anim · Ui · Assets · Environment (`reference/06-*`).

## What never worked (`kit/knowledge/vault/code/graveyard.md`)
Green specs as proof of a working game (the Sfx / Moves runtime and the console-error playtest were never Studio-proven).

## Traps (the full list: `lune run kit lessons code`)
Lune specs have no Vector3 global (Rules take plain {X,Y,Z}; `Guard.vector3` server-side) · camera zoom limits are
Player properties · auto-equipped tools land in the character, not the Backpack · `SetNetworkOwner(nil)` before
server pushes · never re-weld a first-person tool per frame · `wally install` kills a running rojo serve · selene's
error count is the line before the last two · python modules across lanes need unique names.

## Read next
`reference/02-a-new-game.md` · `reference/03-a-new-system.md` · `reference/04-combat-moves-as-data.md` ·
`reference/07-proven-libraries-*.md` · `kit/knowledge/vault/code/index.md` · `[[shared/studio-mcp]]`.
