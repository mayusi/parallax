<!-- reference for the parallax-anim route card; verbatim from the skill page (2026-10-16) -->

## Gate thresholds
Override per spec under `"gate"`: `foot_slide` 0.1 studs/frame (planted feet), `foot_skate` 0.15 (locomotion, vs the
ground speed), `pop_deg` 15, `loop_seam_deg` 2, `hit_before` 1 / `hit_after` 3 frames (a Hit with no fast motion
fails), `penetration` 0.08 studs below the rest floor. A foot's contact and penetration are measured at its SOLE'S
CENTRE (a tilted box's corner dips 0.5·sin(tilt) — an R6 leg at 30° would "penetrate" 0.25 studs at every plant);
every other part at its lowest corner. In a locomotion clip the frame a foot lands or lifts may settle but not
skid more than `foot_slide`. Selftest fixtures in `kit/selftest/anim`. `kit verify` runs the gates on every clip
and refuses a clip made from an older source file, generator (kit/anim/gait.py, strike.py, retarget.py or bake.py, together with clip.py
they compute with) or rig file (their sha256s ride in the clip's `source`); a change to the R6 fold itself
(kit/lib/anim.luau) shows as drift in `src/animations/<Name>.model.json`.
