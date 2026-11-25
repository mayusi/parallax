# Changelog

## 3.1.0 — 2026-11-25

### Added
- **Hardware tiers.** Every local model names its tier; `lune run parallax vision setup` fetches only the ~2.4 GB
  core by default (it used to fetch ~47 GB), `--tier vision|gen|all` adds the bigger tiers, `--list` shows each model's
  tier and size, and a gated model a tier would fetch (SAM 3 without `HF_TOKEN`) is skipped with a note instead of
  failing. `doctor` reports the tier the machine reaches (0 zero-GPU core .. 4 full 3D generation) and what the next one
  needs, and fails only on a Tier 0 gap (Blender is Tier 1, no longer a hard requirement).
- **`lune run parallax upgrade`** updates the kit in a game from a GitHub release: `--check` first, the SHA-256
  checked before anything is unpacked (a bare digest or `sha256sum`'s form), a release holding a link or a path out of
  its folder refused, a backup put back exactly on any error while the kit's files are replaced (`kit/`, `src/kit/`,
  `parallax.luau`, `rokit.toml`; the three newest backups are kept), and four zones (the kit's code replaced - only
  files a kit install or upgrade put there are removed, so a file you added under `kit/` stays through every upgrade;
  starter content and lessons only added to; the vault merged with your lessons, verdicts and rules kept; your game's
  code and content left alone). The new kit's `init` runs last; if it fails, `upgrade` fails and names the command that
  finishes it. `install` and `update` record `kit/UPSTREAM.json` for it (a kit from a local clone says so - an update
  from a clone replaces a release's record - and `sync` still updates from that clone). Maintainers build the two
  release files with `kit/scripts/release_archive.py`.
- **No local LLM required.** Where a local VLM would judge (a design review's bans and pillars, reading text in a
  reference, screening a design exploration against its bans) and none is installed, the kit hands your AI client a
  packet - the pictures and a `PROMPT.md` - and records its answer with `--record` (`kit design review ... --record
  <verdict.json>`, `kit design explore <Piece> --record <answers.json>`, `kit refs read --packet`). An exploration
  writes no direction sheet until its ban screen is answered; answers are refused for other pictures than the packet
  asked about (each plate is held by its SHA-256) and a review's for an asset rebuilt since; a review answer needs both
  lists. The local VLM is now part of the optional vision tier.
- **The engine seam**: `"engine": "roblox"` in `kit.config.json` (the default); `doctor` shows it, and a planned engine
  (godot, unreal, unity) is answered with the roadmap in [docs/ENGINES.md](docs/ENGINES.md).

### Changed
- **Parallax is an MCP tool.** The repository ships no AI-client files (no `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`,
  Copilot / Cursor / Windsurf / Roo / Cline rules, skill copies or client configs). The MCP server sends the kit's
  rules to every client as its instructions and serves each lane's full recipe with its case table.
- **`lune run parallax connect <client>`** sets up only the client you use: its MCP config, plus the enforcement hooks
  for clients that run hooks (Claude Code, Gemini CLI). Codex, Windsurf, Cline and Claude Desktop get the block to
  paste into their global config. `connect` alone lists the clients; `--remove` takes the kit's entry out.
- **`install` writes no client files** (and now installs the git hooks, which it used to miss: `init` ran before
  `git init`). `harness` keeps the git hooks and the connected clients in step. The kit's entry in a client's config
  is always exactly the kit's own launch: one that already is - by a Python launcher that works on this machine - is
  left as it is (a config shared between machines is not rewritten on each, as long as both have that launcher), and
  any other is replaced whole, so nothing added to it is kept (an env var could switch the gate off or pick another
  program, a URL point the name elsewhere, `disabled` keep the server down); settings of your own go in your shell's
  environment or an entry under another name. The same holds for the guard hooks. Updating a 3.0.0 game (`update` from a
  clone, or `sync`; 3.0.0 has no `upgrade` yet), it removes what that version wrote for every client - instruction
  blocks, rule files, skill copies and the kit's entry in every client's MCP config - keeping your own text and files
  and the client running the update (Claude Code, Gemini CLI); the update says when no client is left connected, and
  `connect <client>` connects yours again.
- Gemini CLI's hooks find the guard from the project folder (a relative path run from another folder blocked every
  write).
- **Uploads need no API key.** `upload` screens every file and writes the exact `open_cloud_invoke` call for the
  Roblox Studio MCP; `upload --record <file> <assetId>` stores each id where the game reads it; `upload --pending`
  lists what is left; `--record` refuses a file whose SHA-256 changed since it was screened; an asset id is accepted
  only as digits or `rbxassetid://<digits>`; a name after a switch (`upload --studio <name>`) is the piece's name. An
  `ROBLOX_API_KEY` in the environment remains an optional headless route.

### Fixed
- `parallax_skill` and `parallax_help` returned only the last 160 lines of their output: a long lane recipe arrived
  without its opening stages. Both now return the whole text.
- A new game's first commit was refused by the lane fence (an install spans every lane); a repository's very first
  commit is no longer fenced - every commit after it is, an orphan branch's too. `install`, `update` and `upgrade` print
  the commit to make, with the fence's word for a commit across every lane (`cross`).
- A new game's `verify` failed on the kit's own starter effects: the scene-breakdown, method, stage and legacy-key
  gates and the VFX vault held them as if they were made in the game (and two tests asked for the author's 100+
  effect library, which is not shipped). A starter whose text is one the kit recorded (`kit/vfx/starters.json`: every
  text each starter shipped with, written in the kit's home only) is now the kit's piece - the validator's own errors
  still hold it, and the making gates and the vault hold it from its first edit; the tests check every effect a
  project has, however few.
- The local VLM counts as installed only when all its files are there at their sizes (a cut-short download handed out
  a crash instead of the packet).
- CI could never fail on a vault that is behind the kit's records (the dry run always exits 0):
  `vault_migrate.py --check` exits 1 when anything is unfiled, and CI runs it and `vault check`; the migrator prints one
  `pending` count that verify and `upgrade` read too.
- The grading record a game grows in `kit/` when it has no kit home (`kit/grades.json`, `pairs.json`, `weights.json`,
  `kit/anchors/`) is the owner's data: `kit status` no longer reports it as an edited kit file, and `upgrade` never
  replaces it (a release's copy is added only where the game has none). `update` / `sync` from a kit home refreshes a
  linked game's copy of the home's record, as before; when it links a game that graded on its own, that game's own
  record - and any anchor render the home's copy would write over - is first kept in `board/grading-kept-<time>/`
  (it used to be replaced without a trace).
- `kit status`: a file the kit did not install among its own files (`kit/`, `src/kit/`) is named with the remedy that
  clears it (move it out or delete it - `sync` never could), after any failing gate. The files the kit writes there
  itself that change nothing it decides (a selftest's parts sheet, Blender's backups, a custom rig named after the rig
  it holds) are not named; one that feeds a gate is (a saliency calibration, a rig claiming a shipped rig's name). An
  edited kit file is restored from what put the kit's files there last: `upgrade --force --allow-dirty --tag <the
  installed one>` after a release (even in a game first installed from a clone; `--from <the file>` after one
  installed from a release file), `sync` with a kit home, `update` from a clone for a kit from a clone whose home has
  moved (never the release route).
- `install`, `update` and `sync` never take a game back: a game holding a later kit than the one it is updated from
  (upgraded to a newer release since) is refused, and `--force` installs the older kit anyway. `sync` in a game whose
  kit came from a clone and whose kit home is gone says so and names the clone route (it called the kit a GitHub
  release); a refused update reaches `sync` with its own reason and next step.
- `harness` also takes the kit's server off a client's list of servers kept off (Claude Code's
  `disabledMcpjsonServers`, Gemini CLI's exclusions) and removes Claude Code's `disableAllHooks`: the kit's server and
  its guard cannot be switched off beside an entry that looks right.
- Linux and macOS: Blender is found the same way by every command and tool (`KIT_BLENDER`, `BLENDER`, the usual
  install folders of each OS with the newest version first, then `PATH` - an old Blender on the PATH no longer wins
  over an installed one); COLMAP and Instant Meshes are found by their names on each OS; client hooks and the MCP launch
  use the Python that exists on the machine (`python3` where there is no `python`); `doctor` reports the Studio MCP per
  OS; the Windows-only `sd-cpp` runner is skipped elsewhere with a note.
- The removed `geocalib-pinhole` model (no caller) is no longer downloaded; stale `roblox-*` skill names in pages and
  messages now read `parallax-*` (the old names still resolve).

### Docs
- A new README (every pipeline's capabilities, stages, gates and limits; enforcement; the learning loop; a roadmap),
  [SETUP.md](SETUP.md) (step by step, written so an AI agent can follow it), [CONTRIBUTING.md](CONTRIBUTING.md),
  [SECURITY.md](SECURITY.md) and a logo.

## 3.0.0 — 2026-11-24

- First public release.
