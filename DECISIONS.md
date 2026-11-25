# DECISIONS.md — Architecture Decision Records (lite)

Format: `## N. Title` → Decision / Why / Rejected. Newest at bottom.

## 1. Disk + Rojo as source of truth

- Decision: `.luau` on disk is canonical. Rojo syncs to Studio. Studio MCP only runs/verifies.
- Why: Roblox MCP has no file-write tool; Git needs files. Verified against official MCP tool list.
- Rejected: Studio-first via MCP (no VCS), Azul/Argon as primary (Rojo 7.7 syncback + two-way covers it).

## 2. Pipeline local+free, models may be cloud

- Decision: all pipeline tooling runs offline, free, license-clean. Orchestrator model can be cloud.
- Why: user clarified "pipeline is local not the AI models". Keeps builds reproducible without API bills.
- Rejected: Roblox cloud generation (`generate_mesh`) as dependency; Open Cloud execution as required (optional stage only).

## 3. Blender MCP = procedural modeling, not diffusion 3D

- Decision: AI writes `bpy`, builds in Blender, screenshots, iterates, headless-freezes to scripts.
- Why: user definition of "3D generation". Deterministic, constraint-compliant, VRAM-independent.
- Rejected: TRELLIS/Cube3D-local as primary (12 GB below spec; a CUDA kernel gap on the newest GPUs). Hosted blockout optional.

## 4. Headless gate + interactive co-model split

- Decision: MCP for interactive, `blender -b --factory-startup -P` for production + `validate.py` JSON gate.
- Why: MCP is stateful/fragile serial; headless is atomic, rerunnable, CI-able.
- Rejected: MCP-only asset production.

## 5. UI via Rojo project.json + native StyleSheets first

- Decision: JSON spec → generator → project.json (`Attributes`/`Tags`) → StyleSheet tokens as Attributes.
- Why: avoids hand-XML fragility; StyleSheets are released native layer. React Lua later only if needed.
- Rejected: Figma as required (cloud, 3-file cap, no offline open); raw XML authoring.

## 6. Verify.json as sole "done"

- Decision: one machine-readable contract (`summary` + `next_action`, exit 0-5) in `.verify/`.
- Why: weak/any-model compatibility — failures must be actionable without reading full logs.
- Rejected: chat-scraped logs as pass criteria.

## 7. Template-repo kit versioning

- Decision: template copy via `bootstrap.ps1`, `.pipeline/VERSION` pin, `task pipeline:update` diff.
- Why: submodules break weak models and non-git harnesses.
- Rejected: git submodule, npm-style kit package.

## 8. Desktop control via Windows-MCP (fenced)

- Decision: `CursorTouch/Windows-MCP` 0.8.7 (MIT, pushed same day as adoption) over
  stdio; tool allowlist excludes PowerShell/Registry/FileSystem/Process/Scrape;
  telemetry off; UIA-first, OmniParser V2 (MIT) only where UIA goes blind
  (Blender viewport, Studio canvas); Jedi-3B (Apache-2.0) as stage-2 grounder.
- Why: only MCP-native desktop control verified alive; 0 GPU; same pattern as other servers.
- Rejected: nut.js (paywalled prebuilds), self-operating-computer (dormant),
  Ferret-UI (NC weights), Aria-UI (no license), file deletion for plugin removal
  (account sync re-downloads — proven twice).

## 9. Specs in, verdicts out — one runner for every discipline

- Decision: every discipline is a library + a `tools/task` command + a gate that prints `summary`/`next_action`
  and writes `.verify/<command>.json`. Models write small specs or short scripts; the kit does the hard parts.
- Why: weak models fail by reinventing infrastructure (axes, baking, export flags, emitter caps) on every task.
  Fewer degrees of freedom + actionable failures = consistent results from any model.
- Rejected: rules-only docs (the v2 state: every discipline except code had only prose and stubs).

## 10. One coordinate convention for 3D: author in Roblox space

- Decision: `rbx.py` takes studs, Y up, -Z front, `rot` == `CFrame.Angles`; it owns the Blender conversion and
  FBX axes. `build_calibration.py` is the single Studio check.
- Why: the two pre-kit assets used conventions 180 degrees apart, unnoticed because neither was imported.
- Rejected: per-asset conversion code; authoring in Blender's Z-up space.

## 11. Procedural SFX with numeric ears

- Decision: JSON recipes → numpy synth → OGG; the gate reports power-weighted brightness, attack, tail, loudness.
- Why: models cannot listen; numbers let them compare a sound to its intent. Magnitude-weighted centroid
  was rejected after it read lowpassed noise ~3x too bright.
- Rejected: sample libraries as the default (licensing per file), DAW-only workflows (not scriptable).

## 12. VFX as JSON presets, broadcast to clients

- Decision: presets are JSON ModuleScripts validated by a pure Luau validator (Lune + Roblox); the server
  calls `Vfx.broadcast`, clients build and play effects locally; textures are procedural PNGs with fallbacks.
- Why: declarative data is the easiest thing for any model to edit correctly; client-side playback is smooth.
- Rejected: hand-built emitters per feature (the old explosion), server-side tweens (replication stutter).

## 13. UI via a spec compiler, not StyleSheets (supersedes 5)

- Decision: `ui/specs/*.json` compile to Rojo `.model.json` with a contrast/touch-target gate; the built
  place is read back with `@lune/roblox` to prove every node exists.
- Why: high-level specs are model-friendly and checkable; StyleSheet rules aren't cleanly expressible in
  Rojo model files today. Revisit when they are.

## 14. Shared modules require siblings by string

- Decision: `require("./Guard")` in `src/shared`. Verified in Studio (require-by-string) and Lune.
- Why: `script.Parent` breaks headless tests; string requires work in both runtimes.

## 15. Parallax is an MCP tool; the repository ships no AI-client files

- Decision: the kit's MCP server carries the rules (`kit/harness/AGENTS.parallax.md`, sent as the server's
  instructions) and every lane's recipe (`parallax_skill`, with its case table). `lune run parallax connect <client>`
  writes only the chosen client's MCP config, plus the guard's hooks where that client runs hooks; `harness` keeps
  the git hooks and connected clients in step and removes what older versions wrote for every client.
- Why: generated rule files for eight clients and four copies of every skill buried the kit, and an instruction file
  is advice an agent may ignore. The rules that matter are enforced where every client meets them - the MCP gate, the
  CLI gate, the stage and quality locks, the git hooks and `verify`.
- Rejected: shipping every client's files "just in case" (clutter, drift between copies); keeping the copies but
  hiding them (they still drift and still read as the product).

## 16. Uploads through the Roblox Studio MCP, no API key

- Decision: `kit upload` screens every file, then writes the exact `open_cloud_invoke` call per file for the Studio
  MCP, which calls Open Cloud with the creator's own Studio login and the permissions they granted per game;
  `kit upload --record <file> <assetId>` stores each id. An environment `ROBLOX_API_KEY` remains for headless runs.
- Why: an API key is a secret people paste into the wrong places; the Studio MCP needs none, and its permissions stay
  in the creator's hands. The moderation gate still runs before anything can leave.
- Rejected: dropping the key route entirely (CI and headless machines have no Studio); having the kit call the MCP
  itself (the CLI is not an MCP client - the agent is).
