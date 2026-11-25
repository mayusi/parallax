---
name: parallax-work
description: The work-board protocol for ANY session in a kit project — arrive (kit start <lane>, kit status), claim, log, finish, hand off. Use at the start and end of every session, and whenever you pick up, pause or finish a piece of work.
---

# parallax-work — how models share one project without losing anything

The board (`board/`) is plain markdown in git. It is how a Claude session, a Codex session, a Gemini session and a
human all work on the same game. Pass `--as "<model>@<harness>"` (e.g. `sonnet-4.6@claude-code`) on every board command.

## Arrive (always first)
0. Load YOUR lane: `lune run kit start <3d|vfx|sfx|ui|world|anim|code|qa|kit> [--for <piece>]` — the lane's boot
   sheet (how it works, its own rules), the first stage's commands and lessons, its open tasks, its last handoff and its
   vault page, in one budget. Work in that one department; leave the others' files alone.
   The lessons are RANKED for what you build: `--for <piece>` (its name + its own brief), else your lane's top card;
   the best first (`kit help --stage`: the top two in full; `kit start`: the top one, clipped), the newest few after
   them (recent tool facts), the closest past pieces with the owner's score and words. Per stage: `lune run kit help
   --stage <dept>:<stage> --for <piece>`. A piece is a name like `town_tester_bed` / `DTDrillSpin` or one with its own
   brief; plain words (`--for "gunmetal finish"`) only search. Lessons shown for a named piece are RECORDED on it (board/citations.json): the owner's verdict on it credits or blames them - so name
   your piece, and commit board/citations.json with your work.
1. `lune run kit status --as "<you>"` — read the brief, IN PROGRESS, READY, the **last handoff**, failing gates
   (pipeline gates; per-item reports below their bar are counted apart) and every department's record.
   The owner watches the same cards on `lune run kit board` (a local web board, every game's board, live): keep
   your card's status, done-when ticks and notes current through `kit task` so the board tells the truth.
   `kit start` / `kit game use` keep that board serving in the background and put claims untouched over 24 h back in
   To do with a note (`kit task sweep [--dry]`); a claim you still hold, touch it (`kit task note`) at least daily.
2. Read YOUR department's page before building (kit start already printed it within its budget; in full:
   `lune run kit status --dept <3d|vfx|sfx|ui|world|anim|code|qa|kit>`)
   — the owner's rules, the GOLDEN set (what the owner loved and the feature that decided it), the GRAVEYARD
   (routes that failed; never retried without the owner's words), the owner's last verdicts. Then the stage you are
   in: `lune run kit help --stage <dept>:<stage>` (its ≤ 5 commands and its gate; `kit help --all` is the wall).
3. Do what `next_action:` says. Failing gate first, then your own in-progress task, then the top READY task.
4. Before working on a task: `lune run kit task claim <id> --as "<you>"`. Claimed by someone else and not stale?
   Pick another. Stale (no update for 24 h)? `--steal` and say why in a note.
5. The OWNER's verdict is the only quality signal. The moment they give one, record it:
   `lune run kit verdict <kind> <name> <0-10> "<their words>" --shown <the picture or sound they saw>` (≥ 7 -> the
   golden set, ≤ 3 -> the graveyard; at 3 or less add `--route "how it was made"` - the graveyard row must name the
   route that failed, not only the piece; the verdict is recorded without it too, and its next_action asks for the
   route). `--shown` keeps one small copy of what was judged in the vault (`<dept>/judged/`, once per file): the kit
   cannot learn the owner's eye from words alone. When you show a piece and ask for the verdict, offer two answers,
   Keep and Redo; record the answer at once: `lune run kit verdict <kind> <name> keep|redo "<their words>" --shown ...`
   (a direction without a number: never averaged, never golden / graveyard; it credits or blames the piece's
   lessons). Never invent a number from "Good, keep going"; a number only when the owner gave one (`--inferred` marks a
   guess, and every count keeps guesses apart: `lune run kit verdict trend`).
   A judge score, an IoU, a median or a green gate is never progress on the look.
   The owner can also write verdicts (and `- rule` / `- never` / `- retire` lines) straight into
   `kit/knowledge/vault/inbox.md` in Obsidian. The vault files the inbox and every lane's own verdict store BY
   ITSELF (`kit start`, `kit status`, every lane command); commit `kit/knowledge/vault` with your work.
   SHOWING HIM A PIECE: `lune run kit review <name>` - ONE local page with the piece's stages in order (3D: model
   sheet, blockout, the newest build's views, the finished piece; VFX: beat chart, timing animatic (a video), style
   sheet, dailies, the finished effect - a scene SET with no effect yet is a piece too: its chart and its animatic;
   animation / world: the look, the finished piece), each with its state (not made, waiting for him,
   approved, changed since he approved, waived, scored), its pictures, a note box and Approve / Redo / Record
   verdict. His click runs
   the kit's OWN command (`kit approve --stage`, `kit vfx chart --approve`, `kit task rework`, `kit verdict`): the
   record is the one the locks read (an approval made there says `via: review-page`), and his Redo notes are board
   cards (`kit task resume`). An approval needs HIS words in the note (the page invents none) and is taken only for
   what the page showed: a sheet redrawn or a chart re-timed while he was typing refuses the click and shows the new
   one, and the command itself is told what was looked at (a sheet's id and pictures: `--expect`; a chart's plan
   and folder: `--expect-plan`, `--measured`) and records nothing when that is no longer what is there. So make
   what he will see BEFORE you show him: a chart edited after its picture or drawn without its test frame, or an
   effect recorded again after its style sheet, shows as "not made" or "changed" with no Approve until it is drawn
   again. Open the page in its own browser tab (it refuses to be shown inside another page's frame).
   The piece is the ACTIVE project's (another game's: `--game <Name>`). `kit review <name> --stages` prints the
   same states for you; `--dry` records nothing (to show the page). It is on this PC only (127.0.0.1): when he is
   away from it, keep recording his own words with the commands above - never click for him.
6. Learning is announced, not remembered: `kit start` says when a distil is due (five new owner verdicts), prints
   the owner's newest words and makes the distil its `next_action` - do it before new work; with no distil due, once a
   week its `next_action` is the lane's tidy (`kit vault garden <dept>` + the record warnings of `kit vault check`).
   What needs no model re-learns BY ITSELF: after a verdict, lesson or rule edit changes what they are distilled from
   (golden, graveyard, orders, rules, lessons, plus the VFX taste rules and verdicts, the UI direction briefs and
   lexicon) the VFX / UI director profiles re-learn, and after every verdict the
   lane's checks re-test against the owner's verdicts (checks.json is rewritten only when a result changed). A lane's
   own gate that FAILS (its report named after the lane: `world check`, `anim ...`, an asset's stages - not `kit verify`,
   not a missing tool) prints the lessons that match its words (`--- lessons that match this failure`), and a failure
   that keeps coming back asks every third time for the lesson that fixes it - write it then
   (`kit lesson <dept> "..." --gist "..."`). Then
   `lune run kit vault distil <dept>` prints the packet; ADD what is new (`--rule "..."`), FIX what changed
   (`--edit "R-<dept>-<n>: ..."`), RETIRE what a verdict killed (`--retire "R-<dept>-<n>: why"`) - the live rules
   (`<dept>/rules.md`) accumulate. Cite the lessons and rules you used on a piece: `lune run kit lesson used
   <ids> --piece <kind> <name>` (the owner's verdict on it credits or blames them). What waits for the owner's
   number: `lune run kit verdict pending <lane>`. Tidy-up proposals: `lune run kit vault garden <dept>`. A lesson is
   ONE fix in at most 1,200 characters, with its one-line fix as `--gist "..."` (shown when it ranks below the top).
   Search: `lune run kit lessons <area> <words>` (ranked, best first). By LOOK: `lune run kit alike <picture | piece>`
   - the past pieces that look closest, each with the owner's verdict (and always the nearest ones the owner judged);
   `kit alike dupes` lists a reference filed twice; `kit alike index` (weekly, in the tidy) takes in new pictures. A
   VFX / UI preview and an animation pick sheet print their look neighbours by themselves - a report, never a gate,
   and a piece keeps its own look (the originality rule). `kit start` also shows the owner's own before -> after
   (a low piece turned high: what changed), the SFX lane's measured ear, and the QA lane's failing playtests. A fixed
   bug: `lune run kit bug "<what>" --spec ... --module ... --line ... --from ... --to ...` keeps it as a regression
   case only when the specs catch it planted back. A lane's TASTE MODEL (`kit taste train|order|off|on <lane>`):
   the nearest pieces the owner scored themselves, by look - never a guess; tested leave-one-out on pairs of
   different looks, ON only with 20+ scored pieces ordering pairs the owner's way 60%+ (it re-tests after every
   verdict; `kit start` says where it stands); it only orders candidates (the anim pick sheet), never a gate.
   FAMILIES (kit/knowledge/families.json): a lesson and a piece get a family (firearm, furniture, slash, aura, hud,
   sword, gun, town...) and ranking prefers the piece's family (`kit help --stage ... --for <piece>` names it); a
   lesson's family by hand: `kit lesson <area> "..." --family <f>`; a family's lessons, golden and graveyard pieces:
   `lune run kit vault playbook <lane> [<family>]`. The Roblox API: `lune run kit docs <words | Class.member>`
   (Studio's own reference, local). Is the ranking finding what sessions use?
   `lune run kit vault eval [dept]` replays every piece whose lessons were named (a report, never a gate).
   Is the lane learning? `lune run kit verdict trend` - per lane: the owner's own numbers apart from guesses, Keep /
   Redo, rejected again, how many rejections a lesson ALREADY covered, and (animation) whether the kit's own warnings
   were on what the owner rejected. The owner's recurring words are CHECKS on the work
   (`kit/knowledge/vault/<lane>/checks.json`: the words, the verdicts that said them, the measure, the threshold):
   `lune run kit checks list <lane>`, `lune run kit checks run <lane> <target>` (anim `<Move>/round_K`, vfx
   `<effect>`) on every new piece, and `lune run kit checks validate <lane>` after new verdicts - the status comes
   from evidence only (proposed reports and never blocks; validated = caught 3+ of the owner's rejections with those
   words and spared 3+ loved / kept / picked pieces; retired when it flags more loved pieces than it catches; the
   pieces a threshold was fit on - `fit_on` - never count toward its own validation). A new recurring complaint
   becomes a new entry with its words and sources; a gate tightens only where a check is validated (stricter only,
   never looser).
   Tools missing for a department: `lune run kit doctor`.
7. A brief that spans SEVERAL lanes (a moveset = animations + effects + sounds + moves): do NOT build it all in one
   session. File it once, in the owner's words, with each lane's part:
   `lune run kit kickoff <Name> "<the owner's brief>" --anim "<its part>" --vfx "..." --sfx "..." --code "..."
   [--game <Game>]` - one task per lane (each with the whole brief; the code task waits for the anim task). Then
   each lane's session (`kit start <lane>`) claims its task and works alone. The moves tie the pieces together by
   NAME (animation, sound events, effects): `lune run kit move` names any piece nothing answers to yet.

## While working
- New work you discover: `kit task add "title" --area code|3d|vfx|sfx|ui|world|anim|qa|kit|design --priority p0..p3 --done "observable check"`
  (repeat `--done` per criterion; `--depends <id>` for ordering). Criteria must be checkable: a command that
  passes, a number, a behaviour seen in a playtest — never "looks good".
- Progress, findings, dead ends: `kit task note <id> "..."` — the next model reads these.
- The board is your memory: write a loose end down THE MOMENT it appears, never "later":
  - the owner asks for something (now or in passing, even "that should be redone"): `kit task ask "<their own words>"
    [--area <dept>] [--on <card>]` — p1, kept word for word; done only when shown to the owner. With no --area the
    lane is read from the words (a tie stays "other"); an ask that JUDGES shown work ("the city looks horrible") is
    also filed as the owner's words in that lane's vault. Words, never a bare card id (refused: use --on <card>).
    Cards stuck in "other": `kit task route` shows where each goes, `--apply` routes them;
  - you are not 100% sure (a guessed number, an untested path, a judgement call): `kit task unsure "what and why"`;
  - you think something you or another session made should be redone: `kit task rework "what is wrong"`.
  Lost track (a new context, a summary, a crash)? `kit task resume --as "<you>"` — what you hold with its open
  done-when items and last notes, then every open owner ask (oldest first, "never started" flagged), doubt and redo.
  `kit start` prints the count and the oldest owner asks; the owner sees them as badges on `kit board`.
- A criterion proven: `kit task check <id> <n>`.
- Stuck on something outside your control: `kit task block <id> "waiting on X"`.
- A real design choice (library, architecture, art direction): `kit decide "title" --decision ... --why ... --rejected ... [--area <dept>]` (board/decisions + a vault note under `<dept>/decisions/`; `kit handoff` refreshes every department index with the last handoff)

## Finish a task
`kit task done <id> --evidence "verify green, playtest smoke pass"` — refused until every criterion is checked
and `kit verify` is green (`--force` only with a note explaining why).
When several sessions share one checkout, `kit verify` here is never green at one moment (someone always holds a
half-edited file): `lune run kit prove [--selftest]` checks the COMMIT out into a sandbox worktree beside the project,
bakes build/ there and runs the gates on it; `kit status` prints when the committed tree was last proven and at which
commit. A gate red in the sandbox names a committed file: fix, commit, prove again.

## Leave (always last, even mid-task)
`kit handoff "what you did" --lane <dept> --next "the next concrete step" --warn "what's risky / not verified" --as "<you>"`,
`kit lesson <area> "..."` for anything non-obvious (it lands in the vault, every project reads it), `kit promote`
only for work the owner rated ≥ 7, then commit everything including `board/` — with a PATHSPEC when other sessions
share this checkout (`git commit -- <your paths>`). Never end a session without a handoff.

## Rules
- One task in progress per model. Release what you won't finish: `kit task release <id> "why"`.
- Don't rewrite other models' notes; add your own.
- `board/BRIEF.md` is the game's north star — update it (with the human) when the milestone changes.
