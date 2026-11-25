Selftest fixture for the scene-breakdown gate (mission 02-vfx 5.1): `preset_without_beats` declares no scene,
`preset_half_breakdown` names a set with a lore brief but no beat sheet and no measured scene colours. Both must fail.
`preset_unapproved_chart` has a complete breakdown but its chart was never approved: it must fail too.
The quality locks (2026-10-21): `preset_model_chart`'s chart was approved by a model (who: model), and
`preset_build_frames` measured its colours from our own build renders (3 of 4 frames under build/): both must fail.
