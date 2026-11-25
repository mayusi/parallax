## Parallax (the Roblox kit) — how to work here (any model, any harness)

`lune run parallax <command>` (= `lune run kit`; `kit` below) builds, checks and tracks everything; act on each
command's `summary:` / `next_action:`. Not pipeline work (a question, docs, git)? Ignore this.

### 1. Start your lane with the request (pipeline edits / builds are BLOCKED until you do)
One department per session; leave others' files alone:
```
lune run parallax start <3d|vfx|ui|anim|world|sfx|code|qa|kit> --prompt "<the owner's request>"
```
It compiles the request (PROMPT-X), finds its CASE (`kit case <lane> "<words>"`), writes the session.
Before a heavy build: `assets/plans/<piece>.plan.json` (tools per part / beat from the menu, after the refs).
It prints the lane's boot sheet, lessons, tasks, last handoff and vault page (GOLDEN = loved, GRAVEYARD = failed
routes). Board: `kit status`.
Claim first: `kit task claim <id> --as "..."`. The owner's verdict is the only quality signal; record it at
once: `kit verdict <kind> <name> <0-10> "<their words>"` (≥ 7 lands in the golden set,
≤ 3 in the graveyard; a judge score or green gate is never progress on the look). Quality steps are LOCKS: a new
piece needs its real source (chart, refs, brief, dossier) and the owner's go-ahead (only when given:
`kit approve <lane> <name> "<their words>" --by owner`); `kit new` waits at 3 unscored. Every command: `kit help --all`.

### 2. Prove — never claim without evidence
- `kit verify` must pass. Several sessions in one checkout? `kit prove [--selftest]` proves the COMMITTED tree.
- Content work: its command passed AND you looked at the evidence (sheet, ears, gate warnings).
- Gameplay feel needs a playtest; none run? Say so in your handoff.
- Uploads: `kit upload`, no API key: Studio MCP `open_cloud_invoke` sends each file; `--record` the id.
- Log as you go (`kit task note|check|done`); owner asks / doubts / redos: `kit task ask|unsure|rework "..."`.

### 3. Leave — hand off (always last)
`kit handoff "what you did" --lane <dept> --next "..." --warn "..." --as "..."`. A non-obvious lesson:
`kit lesson <area> "..." [--stage <stage>]`. Proven and reusable: `kit promote <kind> <name> --about "..."` (both go to the
kit's home; `kit sync` pulls them in). Commit with a pathspec (your files and `board/`), never other
lanes' files (a commit mixing two lanes is refused: write `cross` in the message if meant).

### The originality rule (owner, 2026-10-13 — a MUST for everything)
Every new piece gets its OWN look from its own source's real frames at ANIME / AAA quality. Never re-skin the last
success (the library is for MECHANICS) or swap the genre to be "different". A big reinterpretation: ONE test frame,
then ask.

### Rules that keep the game safe
- **Server is authority.** Clients ask via RemoteEvent; the server rate-limits (`RateLimit`), validates EVERY argument
  (`Guard`), applies rules, then acts. `kit audit` fails on unvalidated remote arguments.
- Shared modules (`src/shared`) are pure: no `game:GetService`, no `Instance.new`.
- Never edit kit-owned (`kit/`, `src/kit/`) or generated files (`build/`, `src/ui/*.model.json`, `.verify/`): change
  the inputs and re-run. Never edit a test, gate or `kit/selftest` fixture to make something pass.
- Installing anything: vet it first (two sources, license, install script read), record it in `VETLOG.md`.
- Free models / plugins / downloaded code: `kit audit` (`require(<id>)`, `loadstring`, `getfenv` = backdoors).
