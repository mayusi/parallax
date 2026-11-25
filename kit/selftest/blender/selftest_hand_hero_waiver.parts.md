# selftest_hand_hero_waiver — part review (kept in sync by the kit; you write the answers)

Every part family gets one line. Answer from the REFERENCES / MANUAL, not from memory, in this form:
`- Part [fp]: real: <what it is on the real object> | attaches: <what holds it> | works: <what it does /
how it moves> | ref: <the picture(s) you modelled it from> | verdict: ok` — or `verdict: fix <what is
wrong>` (a fix verdict fails hero/aaa builds). ref: a photo or drawing of THIS part on the real object or,
when it has none, of the closest SIMILAR part (another make's, an exploded diagram's) — a file on disk:
`lune run kit refs parts <asset>` lists the parts without one and the searches to run (kit refs find).
A part answered by a MEASUREMENT (a pin's diameter, a screw's size) may cite a dimension row instead:
`ref: dims:<id>` (`lune run kit refs dims find "<object> <part>"`).
Every part, inside ones too, needs one: a part answered without a picture or a dims row is not answered.
Look at build/renders/parts/<asset>_parts_todo.png first. A part whose geometry changes goes
back to TODO (its fingerprint changed) with its last answer kept: `TODO (changed since: <answer>)` — look
again; if the answer still holds, remove the `TODO (changed since: ` wrapper, else rewrite it.

- Base [e69efa6c]: real: the stand's base plate (a selftest fixture's steel plate) | attaches: the post stands on it, nothing holds it down | works: holds the post upright, does not move | ref: kit/selftest/refs/revolver_b4_side_ref.png (the fixture's cited picture) | verdict: ok
- Post [6e39db64]: real: the stand's round post | attaches: stands on the base plate | works: holds still | ref: kit/selftest/refs/revolver_b4_side_ref.png (the fixture's cited picture) | verdict: ok
