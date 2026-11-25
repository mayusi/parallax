# PROMPT-X — what the prompt compiler has learned

PROMPT-X (`lune run kit prompt`, the code in `kit/prompt/`) turns the owner's raw words into a repo-grounded prompt for
the model that runs it (LIMITATIONS_FIXES_V4 section 9). This folder keeps only what it LEARNED from verdicts:

- `pareto_frontier.json` — per lane and model, at most 5 candidate rule sets (benchmark accuracy vs tokens); the first
  one's rules are added to every compiled prompt of that lane, each with its helpful / harmful counts.
- `changelog.json` — every accepted delta: the verdict that caused it, the rules added or removed, the benchmark
  before and after.

A delta lands only through `lune run kit prompt evolve <packet.json> <0-10> "<the owner's words>"`, and only when the
10 real failed owner prompts (`kit/prompt/benchmarks.json`) still each carry their guardrail. Never edit these files
by hand. The per-compile traces are working data in `build/prompt/traces.json` (git-ignored).
