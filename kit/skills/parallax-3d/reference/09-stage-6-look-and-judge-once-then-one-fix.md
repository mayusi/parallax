<!-- reference for the parallax-3d route card; verbatim from the skill page (2026-10-16) -->

## Stage 8 — Look and judge: once, then one fix round
The full build (`lune run kit asset <name>`), LOOKED at beside the reference pictures — the sheet, the region
close-ups, `kit vision differ <render> <photo>` — then fresh judges and ONE fix list. The score below is a helper that
counts parts, triangles, materials and creases; it is never the bar of a hero build: the judges' is.
Score components (each in the build report, `facts.quality`):
| component | what it measures | how to raise it |
|---|---|---|
| detail | crease density on flat-lit renders | the secondary forms the REAL object has: plates, inset panels, panel lines, vents on hard surface; boards, battens, hardware on wood |
| empty | blank expanses: no creases AND no visible texture (listed biggest-first WITH coordinates) | give exactly those places what the real object has there: texture, hardware, markings |
| variety | distinct KINDS of small detail (copies don't count) | screws, latches, LEDs, connectors, knurling, cables, text |
| geometry | triangles vs the tier budget (hero ~9k, aaa ~16k; >1.5x is penalised; Roblox caps 20k per mesh) | spend on forms; the report lists the biggest triangle costs |
| surface | edge normals + AO + edge wear + chipping + grime | `material(..., chip=0.4, under=(metal), grime=0.4, wear=0.2)` |
| texture | the texture a player SEES: band-pass contrast of the albedo views (grain, wear, grime, chips, stencils), full credit at 1.2% median — more earns nothing | `pattern="wood"`, `wear=`, `chip=`, `grime=` in crevices, stencils |
| materials | 3-5 zones with clear value steps | frame / panels / rubber / metal / accent |
| markings | text, serials, stripes (hero/aaa) | `a.text(...)`, `P.stripes(...)` |
| silhouette / reference | outline breaks; match to `reference={"side": ...}` | proportions first |
| **craft** | plausibility — a FACTOR on the whole score (named first whenever it costs): wood carved instead of built (4+ grooves / recesses, 8+ carved regions of any shape, or 8%+ of the wood's surface
carved — each cut's own faces are traced through the boolean in every material of the cutter, so a comb carving 37
grooves is 37, fused of two materials or not; wood is judged per face (a block fused into a steel nub is still wood);
lines baked on wood — floater seams — count with the grooves; the wood's surface is what is SEEN, internal parts
left out, plus the walls carved into it, so carving can never carve a model out of being wooden), see-through slits in a mostly-wooden model | separate boards over a dark core; `rbx.Asset(see_through=True)` when gaps ARE the design (a slatted crate, a grille); `a.cut(..., through=True)` when a split is (a clamp ring) |
The score measures DETAIL, not resemblance — proportions and shape language come from the comparison image and
your critique. Use `reference={"side": "refs/x_side.png"}` too when you have a side view (silhouette match %).
**The weights are the OWNER's:** fitted to their blind grades (`kit/grades.json`) and every raw score is mapped onto
their scale. **You never grade — the owner does:** `lune run kit grade <asset> <0-100> "why"` asks them to type the
score again at their own terminal (an agent's shell has none: it refuses), and a blind round they graded on a page
comes in with `lune run kit grades --import <round.json>` — also confirmed by the owner at their terminal, every grade
naming its page and the build it showed (script sha, triangles), a round only once (kit/grading/README.md).
`lune run kit grades` shows how well the score follows them, leave-one-out (each grade predicted without itself), and
the current weights on FRESH grades given after they were fitted (the prospective test); `--write` keeps a refit only
when no metric's own test (a sign test on same-object pairs, McNemar on pass/fail, a bootstrap on rank) says it is
worse than the hand weights (p < .05) and one says it is better (p < .0914 each, so the three together keep a
no-better refit at most one time in four, however many grades there are), so fresh blind grades are the real test. Grades carry the measuring code that saw them
(`rbx_score.MEASURE_VERSION`), the script that MADE the graded build (its sha, written into the build's history when
it was built) and the model's fingerprint (triangles, size); after the measuring code changes, `lune run kit grades
--remeasure` rebuilds every graded build it can find and refreshes it — unless its script changed or it no longer
builds the model the owner saw (the owner's numbers never change).
**The ratchet:** `lune run kit accept <asset> "the owner's words"` locks the build the OWNER approved as a floor — a
later build measuring more than 2 raw points below it FAILS (re-scored with the weights of the day, so a refit never
fails an unchanged build). A floor measured by other measuring code cannot be compared, so it vouches only for its OWN
build: one MADE by its script (the file Blender ran, sha recorded at build time) that is its model (the fingerprint it
kept) passes, warned to re-base; any other build FAILS until the floor is re-based — a floor without a fingerprint
vouches for nothing. Lowering a floor (a drop of more than the 0.1 rebuild noise: small steps cannot walk it down) or
moving it onto another build is the OWNER's: `--lower`, confirmed at their terminal; the one re-base without them is
that same build under new measuring code. Once a floor is COMMITTED, the committed one holds (found whatever the
spelling or the models folder): a change of floor takes effect when it is committed, and no edit, deletion or breakage
of the file moves it; a floor never committed is only its file — commit floors. An empty or unreadable record, or a
repository git cannot read, FAILS the build; a build measured by older code is never accepted; the record keeps the
floor it replaced. Opt-outs
(`see_through=True`, `cut(..., through=True)`) are listed in every verdict (`declared`). **Honest studio:** the hero render shows true
colour (Khronos PBR Neutral at -0.8 EV, a sky the reflections see) — the selftest renders a chart of known
albedos every run, so what you look at is what the owner gets. **Product studio** (the judge's views, their close-ups and
`kit showcase`; the owner's call, 2026-10-07): reflections see a mid-grey room with bright softbox strips and dark
bands, the way polished steel is photographed — under the honest sky a polished slide read as matte primer. Every
MEASURED render (the sheet, the reference checks, the quality floor) stays honest. Worn edges of a BRIGHT metal
(stainless, chrome) burnish lighter than its flats (+0.25 at the most-rubbed edge); a dark one still wears toward bare
steel.

### Region map (once per reference — this is what makes you SEE)
Whole-model sheets hide small things: a detail that is 3% of the image is invisible to you AND to the judges
(vision models lose small subjects; cropping restores them — ICLR 2025 "MLLMs know where to look"). So split the
reference into regions: `refs/<name>.regions.json`:
```json
{"image": "refs/x.png", "regions": [
  {"name": "scope", "box": [x0, y0, x1, y1], "parts": ["Scope"], "questions": ["Is the scope a short, fat ROUND tube ...?", "..."]}]}
```
`box` = pixels on the reference; `parts` = name prefixes of YOUR parts in that region; 4-6 yes/no `questions` about
concrete visible features (shape, counts, sub-parts, finish, markings) — "yes" = the model matches. Every build then
renders each region close-up from the reference viewpoint (`build/renders/<name>_r_<region>.png`) and `kit judge`
pairs them with the reference crops in `build/judge/<name>/regions.png`. Your review must have a line per region
(`- scope: ...`), and the judges answer every question: the kit keeps a reference checklist % and tells you what was
FIXED and what REGRESSED since the last verdict.

### The look-and-judge round
ONE round (rule 9): the steps below once — the judges' fix list done in it — and another round only for what the
look still shows wrong; never a loop of rebuilds to raise a number. Judges move about ±1.5 on their own: `kit judge
--record` says when a verdict is inside that noise of the best before it, and calls three in a row a PLATEAU (the
Glock's material rounds: 59.5 / 58.5 / 58.2 / 60.1, the panels asking for opposite changes) — change structure, or
show the owner. Judges also score harder than the owner (64 where the owner said 85): a packet shows the owner's own
grade of the asset first (`kit grade`; a private asset's anchor stays on its machine).
1. Shape work: `lune run kit asset <name> --geo` (~15 s on a 95-part rifle) — every geometry, mechanism, reference
   and deep per-part check, no bake / export (own verdict `.verify/asset-geo-<name>.json`; the full one is untouched).
   It KEEPS PICTURES (2026-11-11): `build/judge/<name>/geo/` — six views in the parts' own colours (1024 x 768) and a
   pair per hero feature (the reference's box, then the model's same box) — look at them every round; the summary's
   `LOOK:` line says where and names every hero feature that has no close-up.
   Then the full build `lune run kit asset <name>` (bake cache): an unchanged model reuses every group's last maps
   + mesh in seconds; a material change re-bakes only the groups that use it; ANY geometry change (a part moved
   more than ~2x the merge tolerance, ~0.3 mm on a rifle; a face changing material; a part changing group)
   re-bakes every group — each group's AO sees every part. It keeps the same six views lit like a product shot
   (1024 x 768; hero / aaa 1280 x 960), the brief's game camera and the hero features' pairs in
   `build/judge/<name>/builds/<build id>/` (`features.json` lists each pair, or why a feature has none). Part tiles
   re-render when anything they show changed (shapes, maps, joints, real scale). The schematic's take-apart /
   line-art views are rendered only when asked: `lune run kit asset <name> --schematic` (a kept set is marked stale
   as soon as the model changes, and `kit schematic` refuses a stale one). `--rebake` re-bakes and re-renders everything.
   The report says what was re-baked and why (`bakes.why`) and where the seconds went (`timing`). `--fast` skips sheets.
   `lune run kit watch <name>` rebuilds on every save through a persistent Blender (no start-up per build: ~30% faster,
   identical verdicts) — the fast inner loop; `kit asset` stays the full chain.
2. Read `summary` (score, delta vs the last build) and `next_action` (the weakest component + where) — then OPEN
   the sheet. **The score is a helper, never the judge:** it rewards creases, and a model carved full of grooves to
   lift it read as noise (crate, chest and blaster went from 33-47 to 55-58 and were graded 1/100; the clean versions
   scored lower). Never add detail the real object would not have; never accept a score — yours or an agent's —
   without looking at the hero render.
3. `lune run kit judge <name>`, then LOOK at `build/judge/<name>/regions.png` region by region (reference left,
   model right) and the whole-model `sheet.png`. Never design a part from a description — put it beside its
   reference crop first.
4. Write `assets/models/<name>.review.md`: `iteration: <the build you just saw>`, one `- <region>: ...` line per
   region, and 5+ bullets of what is still worse than the reference and what you change next.
5. Make the changes. Rebuild. Hero/aaa: fresh judges (a panel of 2-3, never the builder) score the packet; record
   with `kit judge <name> --record`. If the panel says WORSE than the previous build, revert that change first.
6. **Is this build better than that one?** Ask it as a PAIR — judges pick between two far more reliably than they
   score one. `lune run kit judge <name> --pair [[A] B]` (A/B: `current`, `accepted`, `judged`, `previous`, `i<N>`, a
   build id; one name = current against it; none = current against accepted, else previous): every full build keeps
   six views (front, back, left, right, top, 3/4 — one sticky camera, the same light), its region close-ups and the
   brief's game camera (`view:` — first person, third person, top-down, in the world) in
   `build/judge/<name>/builds/<build>/`. The packet (`pair/judge_<n>/`, 3 by default) shows each item — `overall`,
   the game camera, every region beside its reference crop — as #1 | #2, shuffled per item and judge; the key stays
   in `pairkeys/`. Each judge (a FRESH context of the same model, never the builder, never shown another's answer)
   picks per item for SHAPE and, apart, for SURFACE (roughness, wear, colour), and answers the nine 3D-DefectBench
   defects for both. `lune run kit judge <name> --tally` -> win / loss / tie per item, where the judges split, the
   defects a majority saw (`pairwise.json`, and `pairwise` in the verdict). Where B wins, bring that back.
Optimise as you go: the geometry fix names the biggest triangle costs (tiny repeated details: `bevel=0`, fewer
segments; split detail to `group=` if a mesh nears 20k).

**A photo from any angle against the model:**
`lune run kit fit camera <photo> --asset <name>` finds the camera it was taken from
   (silhouette + CMA-ES; the lens from EXIF — a small subject's silhouette cannot show it) ->
   `build/camfit/<name>/overlay.png` (green = both, red = photo only, blue = model only: red / blue that stays is
   where the MODEL differs). Synthetic cameras come back within 0.2 deg when the lens is known (2-3 deg with it
   free); a real 3/4 M107 photo aligns at IoU 0.82 (the rest is the model's own shape). `--ignore <groups>` / `--exclude "x0,y0,x1,y1"` for parts the photo shows
   differently (a deployed bipod); `--points "Muzzle=x,y;Grip=x,y"` pins a thin object's pose by its anchors;
   `--start yaw,pitch,roll` from a known rough view.
