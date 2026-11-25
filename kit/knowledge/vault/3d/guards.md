# 3D — the guard table (mission 01-3d §5.11)

Every build check that fails on (nearly) every asset, and every one with a documented false result: its record, the
decision and the evidence. Measured 2026-10-16 over the 57 asset verdicts in `.verify/asset-*.json` (selftest
fixtures excluded). A verdict lists only the checks that FAILED, so "failed in" counts verdicts, not runs. Links:
[[3d/routes]], [[3d/index]].

Statuses: **fixed** (the cause is gone, at the guard or upstream) · **report** (still said, never the next step and
never a reason to add anything) · **precise** (narrowed to what it was written for, with a fixture) · **keep** (a true
finding; the producers are fixed instead) · **open** (still to do, with the reason).

## Failing on (nearly) every asset

| guard | failed in | status | decision and evidence |
|---|---|---|---|
| `brief` | 48 / 57 | fixed (upstream) | every made prop had no brief. `kit make` now writes it from the owner's request and `kit plan` gates stage 0 on it (086991a1); the rebuilt hydrant passes. The check stays: the selftest names a model built without asking the owner |
| `quality` | 44 / 57 | report | the composite score never predicted the owner (r 0.60, -30 on the successes) and its advice ("4+ kinds of small detail: screws, latches, LEDs") greebled the starter props to 0.1/10. Now the summary's LAST line ("report: score ... never the verdict"), never the next step while a real check is open (`rbx_validate.REPORT_ONLY`), its fix says "never add what the real object lacks" (test_validate_report.py) |
| `roughness_variation` | 43 / 57 | precise + producers fixed | true on the hydrant (one roughness, 0.000 at every scale: kit make's bare rough=0.6) — kit make now gives the scan the check prescribes; false on the wood chair the owner liked (Wood096 scan, fine 0.076, even at mid / coarse like a new chair): a scanned surface varying at the fine scale passes (test_pbr.py). Flat at every scale is still flagged, scan or not (selftest rough_flat unchanged) |
| `review` | 6 / 57 | fixed | the builder's own 5-bullet critique per iteration; a VERIFIER round on the build just seen (kit judge: a fresh reviewer, same-crop pairs, one edit) now satisfies it |
| `see_through` | 11 / 57 | keep | no recorded false result (MODEL3D_AUDIT §9.3); slat / board gaps the owner sees. Watch: kit make meshes with thin gaps |
| `slivers` | 9 / 57 | open | documented false positive on intended tapers (claw, tooth, blade tip under ~0.85 mm). Mitigated in the report (cluster span + thinnest at); to make precise: tell a tip at an extremity from a shelf between two cuts — needs a fixture of each |
| `reference_<view>_local` | 18 / 57 (3 views) | open | local windows of a traced view below their bar on every asset that has them (7 assets): read next — a real proportion miss or a window bar too strict for photo traces |
| `size_vs_target` | 7 / 57 | keep | no recorded false result: the build is not the size its target says |
| `sharp_edges` | 6 / 57 | open | documented FALSE RESULT: the bevelled share flips on a lofted part (one transition network vs a 10% width line: 84% at 19.2 mm, 0% at 22.9 mm, same edges). Reports `share_unreliable` now; the precise fix (judge the real sharp runs, not the network share) changes a threshold: owner's call |
| `pbr_values` | 7 / 57 | keep | values out of the physical range |
| `faceting` | 5 / 57 | keep | no recorded false result |
| `inside_out` | 4 / 57 | keep | no recorded false result (normals) |
| `sculpt_detail` | 4 / 57 | keep | no recorded false result |
| `part_review` | 4 / 57 | open | the hero's per-part answers in <name>.parts.md: a process check now overlapping the verifier and kit plan's look stage — decide report vs keep with the next hero |
| `view_gaps_<view>` | 4-5 / 57 | keep (warn) | the outline gap windows in mm: they now feed the verifier's worst-place crops |

## The documented false results (MODEL3D_AUDIT §9.3)

| guard | status | evidence |
|---|---|---|
| `sharp_edges` | open | above |
| `cad_solid` | fixed | the cause was a 2D outline kink, not fillets: `cad_run.volume_truth`, `kit cad check` fails `volume_untrue`, the build names the cause (2026-10-10) |
| `quality` | report | above |
| `dark_finishes` / rbx_wear | fixed | burnish compared a linear tone to the sRGB bake buffer: `rbx_wear.to_srgb()` + tests (2026-10-10) |
| `part_match_<view>` | fixed | render state (16-bit PNG after a.project): snapshot-then-set restore, 8-bit ID render, selftest `part_match_depth16` |
| `slivers` | open | above |
| `hidden_parts` | fixed | ray parity fooled by shared faces: inside / outside per part on its own faces |
| `floating_parts` | fixed | ray parity on grazing booleans: a 5-ray vote and a cluster of hits |

## Summaries

`kit asset` prints one line: the groups (triangles, size), the warnings by name, then the score as a report. The
rebuilt hydrant (2026-10-16): `main: 100000 tris, [2.245, 3.571, 2.306] studs (2 warning(s): roughness_variation,
quality) · report: score 25.5/100 (prop bar 55, iteration 1) — never the verdict: the owner's is`; its next step names
the real finding (flat roughness -> a scan / coat / wear), never "add detail".
