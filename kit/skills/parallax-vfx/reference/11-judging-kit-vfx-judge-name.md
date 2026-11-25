<!-- reference for the parallax-vfx route card; verbatim from the skill page (2026-10-16) -->

## Judging (`kit vfx judge <name>`)
Never grade your own effect. `kit vfx judge <name>` builds `build/judge/vfx/<name>/`: one sheet per view from the
Studio booth (the truth) and the player (calibrated), the metrics gate, the preset's intent and the owner's
reference frames from `assets/effects/refs/<name>/` (stills of the target look — ask the owner for them), plus
`PROMPT.md` with the rubric (readability, timing, shape language, colour, impact, polish, fidelity; weighted). Hand
the packet to a FRESH judge (a subagent on another model, <= 4 images), then `kit vfx judge <name> --record
verdict.json`: the verdict is validated (every axis, an overall, >= 3 located gaps naming a layer or a moment) and kept
as `assets/effects/judge/<name>.json` tied to the sheets' hashes — a new recording needs a new verdict. Fix the gaps
in order; re-record; re-judge. The number is the judge's; the score is not the goal, the look is.
