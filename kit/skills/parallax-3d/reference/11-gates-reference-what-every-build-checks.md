<!-- reference for the parallax-3d route card; verbatim from the skill page (2026-10-16) -->

## Gates (reference: what every build checks)
Hard: ≤20k tris per mesh · closed mesh · UVs · floating parts · size vs design · inside-out · every a.expect ·
**quality bar** · **fresh review** (hero/aaa) · **stage** (hero/aaa: every traced view at its bar before detail is
judged) · **coverage** (hero/aaa: each hero feature >= 2 px/mm in some picture) · **pbr_values** (hero/aaa) ·
**cad_solid** (every a.cad part a valid, closed solid).
Warnings: buried parts · palette · symmetry · degenerate faces · brief · routes · coverage (props) · pbr_values
(prop) · roughness_variation · **texel_bar** (a report, listed last and deferred at blockout: a group blurrier than
one texel a screen pixel where its tier is judged - 1028 px a metre for hero / aaa, 257 for a prop - with what a
larger map would give; reference/14) · texture_roblox (a game map above the 4096 the kit has seen Roblox keep).
**Deep, per-part (errors at hero/aaa)** — measured, not judged:
- `part_visibility`: ray-cast from 26 directions; `internal()` parts must be hidden, the spec's `visible` is enforced
  (an internal part you can SEE is part of the look: say `through` in the spec and detail it, or close the opening).
- `fastener_support`: pins / screws / rods / rivets must pass through material — a span in open air is reported in mm.
- `clear:<name>`: `a.clear_path("Bore", chamber, muzzle, radius, why=...)` — nothing may block it (bores, sight lines,
  ducts, doorways).
- `spec_parts` / `spec_attach` / `spec_undocumented`: every spec part modelled and touching what it attaches to;
  every model part described ("what IS this in reality?"). Spec = `refs/<name>.spec.json` (`a.spec("<name>")`), or
  inline for a small asset: `a.spec({"parts": [{"name": "Lid", "what": "...", "attaches": ["Body"]}]})`.
- `mechanism`: every joint through its travel, AND no moving part sitting inside another at rest (surface samples,
  5-ray vote, clustered, each part of the other group tested on its own: two parts sharing a face cannot fool it) — a
  barrel through a wall, a trigger inside its housing; the report says AROUND where (studs) and WHICH parts
  ("TopHousing into LaunchTube +97", "Lid in Wall": every face remembers its part through the group join). The travel
  is checked at five stops (a part passing THROUGH something and clear at the end is caught), with any `after=` joints
  posed. A slide needs something to ride on: rails as long as its travel (the spec's `attaches` catches a housing that
  rests on nothing), and every end of a moving part keeps ~1 mm clear of what it passes (flush faces scrape).
- `slivers`: thin shelves on otherwise solid parts (two parallel faces closer than ~1.5 mm) — left when two cuts or
  outlines nearly coincide. Fix at the source: `rbx_trace.region(..., minus=[(piece, gap_mm)], round_mm=2)` splits ONE
  traced shape into pieces with exactly shared seams and filleted outer corners. Parallel means within ~10 degrees: a
  pointed blade (a sword's tip, a feather) thins out to its point by design and is no sliver.
- `plate_support`: a thin flat part (floor plate, armour plate, panel, badge) must rest on its host over >= 70% of its
  back — build it from the host's own edge, not a box. Seated flush or sunk into the host counts as resting
  (`rbx_parts.plate` sinks 0.002 studs, as a mount should).
- `attach_gaps`: a smaller part seated on a bigger one (spec `attaches`) must not show daylight where they face
  (a grip below its seat, a lid not closing); recesses inside a seated interface (rail slots) are fine.
- `marking_placement`: `a.text` must sit on ONE flat face of ONE part — no pins, holes, edges or air under it.
- `projection_*` (warnings, with `a.project` / `a.decal`): `alignment` — the picture's object is not where its trace's
  frame says (said in px: re-trace the picture you paint with); `coverage` — under 80% of what a view sees lands
  inside its outline (the silhouette differs there, or `ignore=` misses a group); `match` — seen from its own camera
  the finished map is not its picture (another layer paints over it, or tex= is too small for its detail; in detail
  mode: its fine structure correlates under 0.3 with the picture's); `detail` — a detail projection moved a
  material's mean colour over 4/255 or transferred no structure (raise `detail_px=`, or the picture has none);
  `decal` — a decal painted nothing (check at= / size= / view).
- `lines_<view>` (its own step after the build, kit/vision/lines.py): one edge detector (TEED) reads the reference
  photo and a shaded render of the model in the same frame; every line INSIDE the outline the photo shows (a receiver
  seam, a magwell plate edge, a row of slots) must have a model line within a few px, and back. Windows along the
  length name where lines are missing / extra; `build/renders/<asset>_lines_<view>.png` = photo / model / diff (red =
  the photo's line the model lacks, blue = extra). hero/aaa FAIL below half the photo's lines; skipped (and said so)
  without the vision models. A reflection or a print that is not geometry: put a `dont_care` box on it.
- `part_review`: every part family gets a tile in `build/renders/parts/<asset>_parts_*.png` (in context — X-ray when
  it is hidden — and isolated) and a line in `assets/models/<asset>.parts.md`:
  `- Part [fp]: real: ... | attaches: ... | works: ... | ref: <picture(s)> | verdict: ok` (or `verdict: fix <what>`
  — fails the build until fixed). `ref:` is REQUIRED: a picture on disk of THIS part on the real object, or of the
  closest SIMILAR part when the object has none (another make's, an exploded diagram's, a patent figure — `kit refs
  patent <n>`); prose is not a reference. `lune run kit refs parts <asset>` lists every part without one and the
  searches to run (the object's part, then a similar object's: the brief's `similar:` line). Inside parts too. The ones to answer NOW are alone on `<asset>_parts_todo.png` (a --geo check renders just those).
  A part whose shape changes (box, volume, area) goes back to TODO with its last answer kept —
  `TODO (changed since: <answer>)`: look again; if it still holds, remove the wrapper, else rewrite it. Answer from
  the references, part by part; this is where "it looks finished" stops being enough.
