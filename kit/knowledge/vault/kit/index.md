# The kit itself — the department's page

**What the kit is:** one command runner (`lune run kit <command>`) that scaffolds, builds, gates, previews, uploads
and tracks every discipline of a Roblox game so ANY model in ANY harness can drive it from two lines: `summary:`
and `next_action:`. This folder is its home; games live in `games/<Name>/`; `kit install <path>` copies it out.

**The rules that keep it safe:** never edit a test, gate or fixture to pass; never edit kit-owned files from a
project (change the inputs); vet every install (two sources, licence, maintainer, install script read; VETLOG.md);
commit with a pathspec through the owner's git CLI, never a co-author trailer; the owner's verdict is the only
quality signal — a score, an IoU, a median or a green gate is never progress on the look.

**The route (every session):** arrive (`kit status --as "<model>@<harness>"`: the board, the last handoff, the
failing gates, your department's page) -> work (claim a task; one discipline at a time; log progress) -> prove
(`kit verify` + `kit selftest` green; LOOK at the evidence; the owner's verdict recorded with `kit verdict`) -> leave
(`kit handoff`; `kit lesson`; `kit promote` only on an owner verdict ≥ 7; commit `board/`).

**Surface:** `kit help` shows the short way in; `kit help --stage <dept>:<stage>` the five commands of a stage;
`kit help --all` the wall. The vault (this folder) is written by the kit; Obsidian is the owner's viewer.

**Read next:** [[kit/graveyard]] · [[shared/commits-and-sessions]] · [[shared/windows-traps]] · [[shared/images]] ·
[[shared/gpu-rules]] · `kit/harness/AGENTS.parallax.md` · `DECISIONS.md` · `board/plans/missions/AUTONOMY.md`.

<!-- kit:auto -->
Lessons: 65 ([[kit/lessons|folder]]) · Verdicts: 0 · Golden: 0 · Graveyard: 0 ([[kit/graveyard]])
Refreshed 2026-11-24 by `kit vault index`.
<!-- /kit:auto -->
