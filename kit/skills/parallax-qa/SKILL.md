---
name: parallax-qa
description: QA-test a Roblox game like a tester — security audit of remotes, gate self-test (every content gate catches its bad fixture, the vault included), scripted in-engine playtests with a performance probe driven through the Roblox Studio MCP, and the record: every bug becomes a spec + a mutation case; the OWNER's verdict is the bar and the accept ratchet keeps it. Use before calling a feature done, after adding remotes, when importing free models/code, and for performance checks.
---

# parallax-qa — the route card (the detail is in `reference/`; the record is in `kit/knowledge/vault/qa/`)

Start: `lune run kit status --dept qa`, then `kit help --stage qa:<stage>`.

## The rules
1. Never "fix" a failing check by loosening it: fix the game or record the accepted risk (`qa.auditIgnore` in
   kit.config.json with a note why). A flaky check is diagnosed (timing, network ownership), never retried.
2. Screenshots (`screen_capture`) only when a check cannot express a pure visual — max one per iteration; read the
   console, the instance tree and the result JSON instead.
3. Fresh judges find BUGS (a wrong state, an empty flip face, art filtered out); they underrate the owner's taste by
   30-45 points and flip on scale. The OWNER's verdict is the bar; `kit verdict` records it; `kit accept` keeps it.
4. Every bug found becomes a spec case + a mutation case: `kit bug "<what>" --spec <tests/x.spec.luau> --module <src/shared/X.luau> --line "<piece of the line>" --from <as it is> --to <the bug>` keeps it in `tests/regressions.json` only when the specs fail with the bug planted back (`kit mutate --regressions` replants them all; playtest results land in `kit/knowledge/vault/qa/playtests/`); report what you tried, what broke, what is now covered
   (`kit task note`, the handoff).

## The route (4 stages)
| # | Stage | Its gate | Read |
|---|---|---|---|
| 1 | audit | `lune run kit audit`: every `OnServerEvent` / `OnServerInvoke` argument validated (Guard / typeof / a check function) and the handler rate-limited; flags `require(<asset id>)`, `loadstring`, server `InvokeClient`, `getfenv/setfenv`, `FireAllClients` in loops — runs inside `kit verify` | `reference/01-*` |
| 2 | selftest | `lune run kit selftest`: every content gate catches its bad fixture (`kit/selftest/<lane>/`); `kit vault check` is a `kit verify` step (frontmatter, links, indexes) | `reference/01-*` |
| 3 | playtest | `kit new playtest <name>` -> `tests/playtest/<name>.luau` (`-- runs on: Server|Client`; `t.check(name, cond, detail?, fix?)`, `t.wait`, `t.waitFor`, `t.player`, `t.find`) -> `kit playtest bundle <name>` -> the MCP: `start_stop_play(true)`, `execute_luau`, save the JSON, `start_stop_play(false)` -> `kit playtest record`; skim `get_console_output`; the perf probe vs `qa.perf` | `reference/02-*` |
| 4 | record | the result file; exploratory play like a hostile player (spam, far away, while dead, two players, leave mid-action); every finding a spec + a mutation case; `kit accept <kind> <name>` for anything the owner rated ≥ 7 | `reference/03-*` |

## Traps
Lune's `stdio.prompt` fails in an agent shell (owner-only acts stay owner-only) · a kit-started server dies with
the Lune job (WMI breakaway + a per-launch token) · Studio is shared by sessions (`get_studio_state` first; never
close another session's play) · Studio unfocused renders ~5 fps · a registered KeyframeSequence loads
asynchronously in Edit mode (wait for `track.Length > 0`).

## Read next
`reference/02-2-in-engine-playtests-*.md` · `reference/04-rules.md` · `kit/knowledge/vault/qa/index.md` ·
`[[shared/studio-mcp]]` · `kit/skills/parallax-verify/SKILL.md`.
