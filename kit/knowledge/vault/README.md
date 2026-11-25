# The kit's knowledge vault

Everything the pipeline learned, as linked markdown the kit writes and every model reads: one note per lesson, one
note per owner verdict, a GRAVEYARD of rejected routes and a GOLDEN set per department, and shared pages for the
infrastructure every department uses. Obsidian-compatible (YAML frontmatter + wikilinks in double square brackets, no plugin syntax):
open this folder in Obsidian as a viewer; the kit never depends on it.

```
<dept>/index.md        the department's page: a hand-written top (route, rules, what to read next) + an auto block
<dept>/lessons/        one note per lesson (kit lesson <area> "..." writes here; kit lessons <area> reads here)
<dept>/verdicts/       one note per owner verdict (kit verdict <kind> <name> <0-10> "<words>")
<dept>/graveyard.md    routes that failed, with the owner's words and why they are not retried (kit vault grave)
<dept>/golden.md       what the owner loved and the measurable feature that decided it (verdicts ≥ 7 land here)
<dept>/orders.md       the owner's STANDING ORDERS for the lane (kit start prints them first; shared/orders.md = every lane)
<dept>/rules.md        the lane's LIVE rules (ids R-<dept>-<n>), added / edited / retired one at a time by a distil
<dept>/distil.md       the history of each distil (the packet's window, the rules it added, its sources)
<dept>/pairs/          a piece the owner scored low and later 2+ points higher: both verdicts side by side
<dept>/refs/           reference pages (specs, measured facts)
shared/                the vision stack, reference tools, the GPU rule, commits, Windows traps, Studio MCP, images
```

Departments: `3d`, `vfx`, `sfx`, `ui`, `world`, `anim`, `code` (gameplay systems), `qa`, `kit`, `shared`.

## For the owner, in Obsidian

- **Open this folder as a vault.** The graph is coloured by department (3D orange, VFX pink, UI blue, anim green,
  world brown, sound purple, systems grey, QA gold, kit teal). `Verdicts.base` is a table of every verdict, grouped
  by department, with "Loved (7+)" and "Rejected (3 or less)" views. `Lessons.base` lists every lesson. Click a
  column header to sort.
- **Give a verdict without a model: write it in `inbox.md`**, one line under *New*:
  `- ui FieldHud 8 loved the dial` (kinds: asset, vfx, ui, sound, world, anim, system, playtest, kit; 0-10 or
  0-100; quotes around a name with spaces). The next `kit status` or `kit vault sync` files it as a verdict note
  (and a golden / graveyard row) and moves the line to *Filed* with a link. A line it cannot read stays put with
  a note saying why.
- **Steer a lane the same way:** `- rule vfx show ONE test frame first` adds a standing order every VFX session
  obeys (or type it straight into `vfx/orders.md`; strike one through to withdraw it); `- never ui a HUD typed from
  flat rectangles` files a graveyard route in your words; `- retire <words of a lesson>` stops that one lesson from
  being shown (it must match exactly one).
- Only the shared settings in `.obsidian/` are committed; your window layout stays on your machine.

### Safe to do in Obsidian, and what to leave alone (tested 2026-10-18 on a copy of the vault)
- **Safe:** read, search, the graph, the two tables; edit a note's properties (tags, anything); type a remark under a
  verdict or a lesson; rename or move a verdict or a lesson (Obsidian fixes the links, the sync still knows the
  note). The sync recognises a note by what it says, never by its file name or how its properties are written.
- **Your own notes** land in `_inbox-drafts/` (new notes and pasted pictures go there). That folder is never
  committed and the kit never reads it: a verdict goes in `inbox.md`, so it reaches the record.
- **Leave alone:** the names of `index.md`, `golden.md`, `graveyard.md`, `distil.md`, `inbox.md` and the folders
  (the kit writes to those exact paths and would make a fresh one); a verdict's own words (the record quotes you).
- **No community plugins.** Obsidian cannot sandbox them, and a shared vault that switches plugins on is how
  vault attacks spread; the list of switched-on plugins is never committed. Keep Restricted mode on.
- **Open THIS folder, not the project root.** The root has 3,500+ markdown files and none of these settings;
  `kit status` warns while Obsidian is open on the root.
- While Obsidian has the vault open, the sync leaves `inbox.md` alone for 20 seconds after you last typed in it,
  so a half-typed line is never filed.

## Every lane writes here

`kit verdict`, `kit grade` (3D), `kit anim verdict`, `kit ui judge --owner`, `kit vfx vault verdict` and the sound
booth (`kit sfx listen`) all record the owner's verdict. The vault catches up BY ITSELF: `kit status` (every lane),
`kit start <lane>` and every ui / vfx / anim / sfx command (that lane's own store) file whatever the store holds that
the vault does not (file times in `.verify/vault_sync.json`, ~0.3 s), plus lessons and the inbox. Nobody has to
remember `lune run kit vault sync`.

## Working with the record

- **Rules first.** Each department's `rules.md` holds its LIVE rules, each read from the owner's verdicts (a
  hypothesis until the next verdict confirms or kills it). The department page prints them right after the route.
  When five new owner verdicts have landed, `kit start` and `kit status` say a distil is due: `lune run kit vault
  distil <dept>` prints the packet (verdicts, lessons, and the pairs where a no became a yes); then add what is new
  (`--rule "..."`), fix what changed (`--edit "R-3d-2: ..."`) and retire what a verdict killed (`--retire "R-3d-1:
  why"`). Rules accumulate: a distil never rewrites the set, so the ones that still hold survive.

## How the lanes learn (automatic unless it says otherwise)

1. The owner's verdict lands (any route above) and the vault files it by itself: golden ≥ 7, graveyard ≤ 3.
2. Every lesson and rule carries an id (`[L-3d-a1b2c3 +2/-0]` in `kit start` and `kit help --stage`). A session
   cites the ones it used: `lune run kit lesson used L-3d-a1b2c3,R-3d-2 --piece asset barrel`. The owner's later
   verdict on that piece counts for (7+) or against (3-) each one; a lesson cited three or more times with harmful
   ahead by two is FLAGGED, never removed by itself. `kit status` shows how many verdicts landed on cited pieces.
3. Five new owner verdicts make a distil due (announced, not forgotten); rules are added, edited or retired one at a
   time.
4. `kit verdict pending <lane>` lists what still waits for the owner's own number (new pieces, and pieces that only
   have a score a model read from the owner's words), each with the lane's scoring command.
5. `lune run kit vault garden [dept]` lists near-duplicate lessons and flagged lessons and rules with the command
   that would retire each, and writes the before/after pairs. It proposes; it never deletes.
6. `kit new` shows the lane's nearest loved piece (its mechanics, never its look), and refuses while the lane has
   three new pieces the owner has not scored.
- **What replaced what.** `lune run kit vault supersede <newer note> <older note> --why "..."` links the two (the
  newer note gains `supersedes`, the older one `superseded_by`); a superseded lesson drops out of `kit lessons` and
  the page, and the record keeps it.
- **What else touches this.** `lune run kit vault related <note> [--hops 2]` lists the notes linked to it in or out,
  the same piece judged again, and lessons and decisions that name it, one line each. No database, no model call.
- **Decisions.** `kit decide` writes a note under `<dept>/decisions/`; older ones in `board/decisions` are filed by
  `kit vault sync`.
- **Token meter.** `kit vault check` prints what each department page costs as shown and in full.
- **Lessons by stage.** `kit help --stage <dept>:<stage>` lists the newest six lessons of THAT stage under its
  commands; `kit lessons <area> --stage <stage>` lists all of them. A lesson's stage is read from its words (each
  stage's `words` in `kit/knowledge/routes.json`; a word in the lesson's opening counts double, a lesson takes its
  best one or two stages), or set by hand: `kit lesson <area> "..." --stage surface`. `kit lessons <area>` alone
  prints the newest 25; add words to search, `--all` for every one.
- **Rejected again.** The trend line (`kit status`, `kit verdict trend`) counts pieces the owner rejected (≤ 3) that
  were already rejected on an earlier day, and `kit vault check` names each one from the last week. That number is
  the vault's own scoreboard: each repeat is a round the graveyard should have prevented.

## Loading one lane in any harness

- **`lune run kit start <dept>`** loads ONE department for any model in any harness: the lane's boot sheet
  (`<dept>/boot.md`: the boot line, how the lane works, the lane's own rules), the first stage's commands and that
  stage's lessons (`--stage <stage>` for another), the lane's open tasks, the newest handoff that names the lane, and
  this department page cut to what `vault.start_budget` (2,500 tokens) leaves.
- **The boot line** at the top of each `boot.md` is the two lines to paste into any harness to start that lane.
- The shared rules (kit/harness/AGENTS.parallax.md, sent by the MCP server as its instructions) are a short router:
  every rule that belongs to one department lives in that department's `boot.md`, so another lane never reads it.
- **`kit handoff "..." --lane <dept>`** records the lane; `kit start` shows each lane only its own handoffs.
- Every lane's skill page (with its case table) is served by the MCP server (`parallax_skill`) and by
  `lune run parallax skill <lane>`: no client keeps a copy.

## Enforced

- **Every pipeline's own commands show its page first**: `kit ui`, `kit vfx`, `kit anim`, `kit world`, `kit sfx`,
  the 3D commands (`cad`, `trace`, `refs`, `gen`, `judge`, ...), the systems commands (`net`, `move`, `game`,
  `fuzz`, `mutate`) and `kit playtest` print the department's page before they run, once per department every
  `vault.reshow_minutes` (120 by default) so a long session pays for it once (`kit/lib/vaultgate.luau`;
  `KIT_VAULT_PAGE=always|never` overrides). Lookups (`find`, `list`, `--help`) skip it.
- **`kit verify` fails while the vault is behind**: the "vault in step" gate counts what a sync would still
  write (verdicts, lessons, golden / graveyard rows, inbox lines); anything above zero is red until
  `lune run kit vault sync` and a commit of `kit/knowledge/vault`.
- `kit verify` also fails on a broken note (no frontmatter, a dangling link, a score off 0-10), and `kit promote`
  refuses work without an owner verdict of 7 or more.

- `lune run kit status` / `kit new <kind>` print a department's page within `vault.budget` tokens (kit.config.json).
- `lune run kit vault page <dept> [--full]` — the whole page. `kit vault check` is a `kit verify` gate: frontmatter
  (`area`, `kind`, `date`), links that resolve, an index per department.
- `lune run kit verdict list [kind] [name]` — the owner's record, newest first. The owner's eye is the only bar.
- Weekly: `kit verdict trend` (per department: n, mean, the last 7 days vs the 7 before, every piece's trajectory —
  a report, never a target); `kit vault check` also prints a "weekly" block of warnings that never fail verify
  (a golden row whose piece was rejected LATER, a golden row with no verdict note, a grave without a reason or a
  source, a verdict with no words); `kit vault distil <dept>` packets the verdicts + lessons since the last distil
  and `--rule "..."` x3 records a model's reading of them in `<dept>/distil.md` (the owner's next verdict confirms
  or kills each rule).
- Never edit a verdict's words. Never delete a graveyard row (a route that later works gets a golden row).
- `kit/scripts/vault_migrate.py` filled it from the old stores (2026-10-16) and is idempotent.
