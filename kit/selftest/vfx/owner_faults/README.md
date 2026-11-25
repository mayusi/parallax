# The owner's real bad examples (VFX) — kept as they were judged

Each folder is a piece AS THE OWNER JUDGED IT: the preset version current at his verdict
(`library/vfx/effects/<piece>/versions/`, the newest snapshot before the verdict time) and, for the recording gate, the
hero view of the recording he saw (`library/vfx/effects/<piece>/previews/metrics.json` + `expanded.json` at the commit
below, trimmed to what `summarize()` reads: the frame layers, hits, hitstop and the hero view). Reworks never touch
these: a rule or gate that passes one of them lies about his words. `kit selftest` runs them (kit/cmd/qa.luau).
Never edit a fixture to make a check pass — fix the check.

| piece | his verdict | judged version / recording | the check that must catch it |
|---|---|---|---|
| seam | 6 — "Bad impact frames" (2026-10-24) | recording at 4929a6d4 | recording gate `frames_on_screen` (re-framed frames over 0.008 of the hero view) |
| sandfall | 6 — "Bad impact frames" | recording at 5c98fe8d | `frames_on_screen` (0.017) |
| quicksilver | 6 — "Meshs and Impact frames very low quality" | recording at 1aec0da7; preset 20261024-191034-a6b6b75b | `frames_on_screen` (0.005); taste rule `untextured-solid-mesh` (8 of 8 SmoothPlastic) |
| noctiluca | 6 — "The impact franes are bad" | recording at 137e7467 | `frames_on_screen` (0.000) |
| quenchstrike | 6 — "The Effects like Smoke looks horrible" | preset 20261024-190423-ae4bd883 | taste rule `lit-puff-swarm` (9 + 18 lit gpu_smoke cards) |
| nuke_v3 | — "the smoke looks bad around and the explosion cutzx off at the top" (2026-10-22) | preset 20261022-120546-2dd03439 | `lit-puff-swarm` (four 110/s lit gpu_dust_puff surges + haze + stem dust) |
| nuke_v2 | 8 — "could be improved in ways like the smoke around it and how it fades" | preset 20261022-102132-3b845624 | `lit-puff-swarm` (his named fault on a liked piece: the rule's evidence, not a blunt rule) |

Pieces that must PASS (the loved side of the same checks):

| piece | his verdict | judged version / recording | must hold |
|---|---|---|---|
| starblade | 9.5 — "GENUINELY UR BEST WORK" (round 6, 2026-10-12) | recording at 1530a819 | `frames_on_screen` (re-framed frames over 0.43 / 0.13 of the hero view) |
| sumi_seal | praised — "They really look amazing" (2026-10-24, the first four originals) | recording at 4e2a8a85 | `frames_on_screen` (a closeup over 0.058) |
| nuke_v4 | 8.7 — "WOW THAT LOOKS LIKE A 8.7/10" (2026-10-22) | preset 20261022-130522-b8055511 | every taste rule (the same mushroom as v2 / v3 with ONE simulated surge card) |

Not caught, said honestly: hoarfrost 4 ("Impact frames look eh") — its strike WAS on screen (0.079); its frames were the
borrowed shatter motif, not frost. No check measures that yet.
