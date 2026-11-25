# QA — the department's page

**The truth:** QA decides what "done" means, and the OWNER's verdict is the bar. Fresh judges find BUGS (a wrong
state, an empty flip face, art filtered out) — they underrate the owner's taste by 30-45 points and flip on scale.
Never loosen a check to pass; a flaky check is diagnosed, not retried; screenshots only where a check cannot
express a pure visual (one per iteration); every bug found becomes a spec + a mutation case.

**The route:** audit (every remote handler's arguments validated and rate-limited; no `require(<id>)`,
`loadstring`, `getfenv`) -> selftest (every content gate catches its bad fixture; `kit vault check` too) -> playtest
(scenarios through the Studio MCP: start play, inject, collect the console, stop; any error fails) -> record (the
result file; the regression corpus; `kit accept` for every kind).

**Read next:** [[qa/graveyard]] · [[shared/studio-mcp]] · `kit/skills/parallax-qa/SKILL.md`.

<!-- kit:auto -->
Lessons: 19 ([[qa/lessons|folder]]) · Verdicts: 0 · Golden: 0 · Graveyard: 0 ([[qa/graveyard]])
Refreshed 2026-11-24 by `kit vault index`.
<!-- /kit:auto -->
