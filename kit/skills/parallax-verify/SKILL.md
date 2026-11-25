---
name: parallax-verify
description: Prove work is done before claiming it — run the gates, read only summary/next_action, look at the evidence, commit only on green. Use before saying "done", before marking a task done, and before every commit.
---

# parallax-verify — proof, not claims

1. Run the command for what you touched: `lune run kit asset <n>` / `sfx <n>` / `vfx` / `ui` / `playtest ...`.
2. Run `lune run kit verify`: format → selene → types → tests → VFX presets → UI drift → security audit → build.
3. Read ONLY `summary:` and `next_action:`. Failed? Do the next_action, re-run, repeat until green.
   Formatting: `lune run kit format`. The full detail is in `.verify/<command>.json` if you need it.
4. Look at the evidence — a passing gate is necessary, not sufficient:
   3D → `build/renders/<name>.png` (one 2×2 sheet) · sound → the "ears" in `.verify/sfx-<n>.json` ·
   UI/VFX → gate warnings · gameplay → a playtest (`parallax-qa` skill).
5. Couldn't playtest or look? Say so in the task note and the handoff. Never imply you checked what you didn't.
6. Never edit a test, a gate, or a `kit/selftest` fixture to get green. Changed the kit itself? Also run
   `lune run kit selftest` — every bad fixture must still be caught.
7. Commit only when `kit verify` exits 0. Check the exit code itself — don't let a pipe (`| tail`) hide it.

Exit codes: 0 pass · 1 lint/format/types/audit · 2 tests · 3 build · 4 playtest · 5 toolchain (`kit doctor`) ·
6 content gate · 7 wrong usage (read next_action).
