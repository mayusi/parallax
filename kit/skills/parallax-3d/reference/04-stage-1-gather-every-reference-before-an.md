<!-- reference for the parallax-3d route card; verbatim from the skill page (2026-10-16) -->

## Stage 1 — Gather: every reference before any shape
**The dossier first — what is KNOWN about a real object, graded** (`lune run kit dossier ...`, kit/refs/dossier.py).
Compiled ONCE per real object and reused by every asset of it (`kit/knowledge/<slug>.json`; a private one in
`~/.cache/roblox-kit/knowledge/`); `kit plan` holds Gather until the owner approved it. From just a NAME:
`kit dossier new "<object>" --category <pistol | rifle | generic> --maker-domain <the maker's site>` prints the
category's research list (kit/knowledge/categories/) — follow it in order: the maker's own page for THIS variant, its
owner's manual (parts list with numbers, exploded drawing, field-strip order, a technical data table that names the
sibling variants' numbers too), its patent list (design patents draw clean orthographic views), its own pictures (a
360-degree turntable: one distance, one light — the best measuring pictures), then CC pictures and reference models.
A maker's turntable is also a MODEL: `kit refs hull <folder of its photos> --length-mm <the A length> --name <name>
--side-col <the side photo's column> --front left|right` finds the camera from the photos themselves, carves the
object's visual hull, scales it to the published length and MEASURES the rest (its height and widths check the other
published sizes), and renders the square top / front / side OUTLINES no camera takes (add them with `--kind
drawing`, the hull with `--kind model --measure refs/<name>.measure.json`) — outlines only, their widths upper bounds;
its rear outline is its front one flipped (the check calls a mirrored copy the same picture: add one). Views WITH
detail (a rear sight, a backstrap) come from a confirmed reference model: `kit refs measure <model> --name <n>
--length-mm <A length> --views all [--front min]` renders its shaded square side / top / front / rear at 6 px/mm
(`build/refs/<n>_<view>_view.png`; LOOK that the front points right first). A reference model with an accessory (a
weapon light) is measured without it: `kit refs measure ... --skip <word>` — else its length scales the gun wrong.
Then CUT the build against the model: `kit refs sections <name> --ref <library id> [--ref-hide <word>] [--flip]` —
cross-sections at the same stations behind the muzzle (dense at the nose), the reference red over ours blue, each
station MEASURED apart (p90 mm; the reference's shape our build lacks, ours it has not): a solid where the real part
is hollow, a box where it is round, a spring 4 mm too high — none of it shows from the side (the Glock's frame and
nose, 2026-10-10). Do it at the Shape stage for every hero part, before any surface work.
A PHOTO carries its camera's perspective (the Glock 17's 35 px/mm side photo came out 2.4% too tall, its dust cover
1.9 mm thin, its grip 1.6 mm long): lay its trace onto a CALIBRATED outline of the same view — the turntable hull's,
a confirmed model's square view — with `kit refs rectify <photo trace> --to <calibrated trace> --level <slide>` (one
projective map, found edge to edge, taken out of every outline, hole and part), then `kit refs profiles <name>_rect`
and build FROM the rectified profiles; a number measured by hand on the raw photo goes through the same map. A HERO
build is matched against EVERY traced view it has (`assets/models/<name>_*.trace.json`, found by name, IoU 0.9 — the
Glock build once had traces and no trace_match at all); a trace made from data found wrong is excluded with its reason:
`a.not_reference("<trace>", why="...")`; where a reference differs on purpose (a model's night sights, flattened
levers) a `dont_care=` box with the reason in a comment.
A size the maker publishes OVER a part (GLOCK's 34 mm width is over the slide stop levers, which a hull carves away
and a model flattens) is recorded beside it, measured ON the confirmed models WITHOUT that part: find where each
model's extremes are (a model's box is lever + magwell + tilt, not "the body"), `kit refs measure <model> --name <n>_cut
--cut <L0..L1>,<H0..H1>` (mm from the rear / from the bottom: the sizes without that box, recorded), then `fact --dim
"width without slide stop levers" --mm 31.8 --from <model id> --measure refs/<n>_cut.measure.json` — B at most (two
independent sites agreeing), the number checked by script, its MEANING by two keys (one blind). Named in the category's
`frame`, a view or model then passes against either meaning (and says so: "checked against ... measured ON the
reference models"). A row added wrong: `withdraw <object> row:<id> --why ..` (its adder or the owner; a reviewer rejects
instead). One model is ONE source however many pages or files carry it; a hull's OBJ is right-handed (right side +z).
Record as you go: `source --url .. --kind manual --fetch`, `fact --part slide --dim length --mm 186 --source s1
--quote "<the page's words around the number>"` (refused when the page does not say it), `part --no 1 --name Slide
--quote "1 Slide"`, `tell --text "no finger grooves" --vs "<sibling>" --quote ..` (what sets this variant apart),
`add --url/--file <picture> --page <where it came from> --scope measure-only|ship-ok --view side-left` (a private
asset may use the maker's photos as MEASURING references only — never shipped, never committed; the files live outside
the repo; the owner's own photo: `--scope owner --as owner --note "<when they gave it>"`),
`add --kind model --measure refs/<name>.measure.json`, `withdraw <id> --why ..` for one added wrong. `kit dossier
check` grades every fact, measures every picture (px/mm, proportions against the A/B facts, duplicates) and every
model's proportions, and scores what the category needs (views, close-ups, anatomy, tells, models). Then review in ONE
batch: `kit dossier review "<object>" --as <you>` (look at its contact sheet, answer each item: object, variant and
the tells you saw, stock, view, square-on, what it is good for), and a FRESH reviewer `--blind` (no claims, no earlier
verdicts) — an item counts once two different reviewers accepted it, one blind, one not its adder. `kit dossier sheet`
-> the reference sheet for the owner; on their yes, `kit dossier approve "<object>" --as owner --sheet <the id on the
sheet they saw> --note "<what they said>"` (stale the moment anything graded changes). A number typed from memory
never counts; a file path is no source; the owner's own measurement is `fact --source owner --as owner --note ..`. Then `kit pack <name> object "<object>" --length dossier` and
`kit pack <name> size <part.dim> dossier` take the graded sizes (A / B only). Web search ranks machine-written content
farms above the maker: `kit/knowledge/sources.json` blocks the ones found — add every new one a reviewer finds.
Everything below happens BEFORE the first shape: pictures of every side and every part (sharp), sizes with sources,
1-2+ reference MODELS measured and looked inside, the colours measured, each hero feature at >= 2 px/mm. Start the
stage-2 generators as soon as the first views are cut out — each when the GPU is idle (never beside SAM tracing),
the CPU work (sizes, reference models, the parts plan) meanwhile.
**The pack — every result in one place** (`lune run kit pack <name>`, `assets/models/<name>.pack.json`): it FINDS what
the asset has by the kit's own naming (traces and their mm profiles, the reference models measured / inspected under
its name or cited by its script, generated drafts, lighting-free colour pictures, fitted proportions) and KEEPS what
you choose: `kit pack <name> object "<what it is>" --length dims:<id> --category <kind>` (the real length every size
hangs on), `kit pack <name> size slide.length dims:<id>` (a size with its source; plain mm is said UNSOURCED),
`kit pack <name> colours --trace <name>_photo_side` (each traced part's MEDIAN colour, roughness and metalness inside
its own mask on `kit vision albedo`'s lighting-free picture — run that first), `kit pack <name> time <stage>
<seconds>`. The build reads it: `pk = a.pack()` → `pk.length_mm`, `pk.size("slide.length")`, `pk.profile("slide")`
/ `pk.extents("slide")` / `pk.outline()` / `pk.holes()` (mm, kit refs profiles' frame; the SIDE view's unless `view=`
or `trace=` names another — a front view's slide is its width), `pk.colour("slide")` (LINEAR,
straight into `a.material(color=)`; `pk.colour_srgb` as measured), `pk.rough` / `pk.metal`, `pk.levels("<model>")`
(a reference model's slices), `pk.draft()` (the generated GLB). Every build scans the asset's files again (a profile
traced after the last `kit pack` is read); the CHOSEN values (object, sizes, colours) are part of the build's identity
(another colour = another model for the grades and the ratchet). A value the pack lacks raises with the command that
fills it; the verdict lists every value read (facts.pack, unsourced ones named — a bare number or length given
without a source) and `kit plan` says when the pack holds sizes or colours but the build script never opens it
(no `a.pack()`).
**Reading the pictures (local, offline):** `lune run kit vision view <picture>` says which view a picture is (front,
side, back, top, 3/4); `vision similar <a> <b>` scores how alike two pictures look and `vision differ <a> <b>` shows
WHERE they differ (two candidate references; later, a render beside its photo); `vision depth <picture>` gives
relative depth (where a form bulges); `vision vectorize <picture>` turns a drawing's lines into SVG curves to read
(the build takes its outlines from `kit trace`); `vision upscale <picture> --x 4` enlarges a small picture before it
is traced. `kit refs rank <folder> --what "<object>"` orders a search's pictures by the same models; `--not "museum piece, votive copy, car"` sinks what the pictures must NOT be (its title names it, or the model reads it as that more than as the object) - the car rim's first search ranked museum wheels first.
**Can the pictures show it?** `lune run kit refs coverage <name>`: pixels per mm for each hero feature in each picture
that shows it (a traced view by its own scale, a close-up by its box over its size). Under 2 px/mm at best, nobody can
model it from that picture: `coverage` warns a prop and FAILS hero / aaa — ask the owner for a close-up picture (or
make a clean view, low trust) BEFORE modelling the ornament from 145 px. EVERY part, not only the hero features:
`kit refs coverage <name> --parts [--fetch N]` — each part's best px/mm among the pictures its answer cites (a traced
view, or a library tile / close-up at its known scale), "measured" when it cites a dims row; a part under 2 px/mm or
cited only with photos of unknown scale gets a close-up at a KNOWN scale (`kit library inspect <uid> --part <words>`)
or a search (`--fetch` runs `kit refs find "<object> <part> close up"`).
**Real objects: research → spec → trace → model (in that order).** Never model a real object from one photo.
1. References: a TRUE SIDE VIEW (the maker's product shot, a manual / patent drawing, a blueprint — a 3/4 photo traces
   wrong everywhere), plus the manual / exploded view for what is INSIDE and how it works. Log each in `refs/SOURCES.md`.
   Its lighting: `lune run kit vision light <picture>` -> an HDR map (.exr) + where the key light is, key:fill, kelvin.
2. `refs/<name>.spec.json` — written from those BEFORE modelling: `length_mm`, `height_ratio` (published dimensions),
   `features` (u/h or mm boxes that must be solid / gap, checked against the trace) and `parts`: every part with
   `what` (and the manual's item number), `attaches` (must touch), `visible` (exterior | through | hidden), `source`.
   Names ending in `*` match a prefix (`"Scope*"`). `a.spec("<name>")` makes the build check all of it.
3. `lune run kit trace <image> --name x --spec refs/<name>.spec.json [--exclude box --protect box --part name=box]`
   — red tint in the preview = what an exclusion REMOVED (never the object: `--protect` it), `--part` traces what you
   removed (a bipod) as its own outline. Transparent PNGs trace from alpha (exact). Fails on perspective / wrong
   proportions / spec features not where the spec says. With the vision models (`lune run kit vision setup` once —
   vetted, pinned, free, offline): `--cutout` takes the object mask from a learned cutout (photos on a REAL background
   trace like studio shots), and `--part-point grip=x,y` traces ONE part's own outline from a single click on it (SAM
   2.1; `--part-box name=x0,y0,x1,y1` from a box; more clicks: `--part-point "grip=x,y;x,y"`, quoted) — a grip, a
   guard, a stock as its exact shape, never "everything in a box". Trace every part you model from its own outline.
   One click on a BIG structure (a stock, a receiver) returns the whole object: the trace then fails "PART = WHOLE
   OBJECT" — give that part a `--part-box`. `--part-text grip="pistol grip"` prompts a part by WORDS (SAM 3, run in
   the TRELLIS.2 environment: the best match; `name="phrase"#2` the 2nd). Every part's mask is JUDGED (trace JSON
   `part_quality`, the summary says "DOUBTFUL part mask(s)", the preview draws them magenta): a box prompt's mask
   filling > 92% of its box (SAM took the region), two masks sharing > 30% of the smaller (grip and guard as one
   area — a real SAM 3 run on a sword gave "sword crossguard" and "sword handle" 99% the same mask), a box-prompted
   mask stopping short while the object runs on as a thin piece (a dropped claw), a plain `--part` box. Retrace a
   doubtful part (more clicks, other words) BEFORE a spec "ref" links it. Spec `gap` features are checked on the
   traced silhouette WITH its openings (a thumbhole, a trigger guard). The trace records where its frame sits in the
   picture: `rbx_trace.px(t, x, y)` turns a pixel you read off the reference into design units exactly. A click that
   lands on the backdrop fails the trace ("PART CLICK OFF THE OBJECT": read clicks off the ORIGINAL picture, not a
   resized copy).
   The outline comes out as SMOOTH CURVES (the true edge, sub-pixel; sharp corners kept where two straight edges
   meet): `rbx_trace.smooth(t, part="grip", flat=0.0003)` samples them as finely as the triangle budget allows (a
   round grip stays round). `--straighten` undoes a photo's perspective; `--ortho` marks a render, a drawing or a flat
   object shot square-on that IS orthographic (a taper is real: no perspective check). A polished blade on a white
   backdrop loses half its width to the backdrop colour — trace it with `--cutout`.
   **Build every part FROM its trace — the hero discipline (the owner, 2026-10-07: "not enough data collected properly
   AND NOT USING THE DATA"):** (a) per part, the SHARPEST picture of the real object you can find: `lune run kit refs
   find "<object> <part>"` fetches originals (up to 40 MB), `refs patent` the drawings, `refs coverage` must say >= 2
   px/mm; a low-resolution design picture (a game render) is upscaled first (`kit vision upscale <pic> --x 4`) and
   traced with `--tolerance 1.0` (a 250 px picture traced coarse gave 41 points: its hammer was one straight line).
   (b) trace each part with its own prompt — a box AND clicks, `!x,y` on what SAM keeps swallowing (`--part-box
   "safety=x0,y0,x1,y1;x,y;!x,y"`) — then LOOK at every part on its picture: `lune run kit refs crop <trace> --f a..b
   --h a..b --parts p,q` (a mm grid, the outlines). A wrong mask is RETRACED or a better picture found, never modelled
   (the Silverballer's grip safety had swallowed the thumb safety; the mag catch its shadow ring — both caught here).
Only a NAME, no picture? `lune run kit vision concept "<name + details>"` draws a turnaround sheet (front, side, back,
top; FLUX.2 klein, local) to agree the look in the brief — a concept, never a measurement (sizes: real refs).
**Clean views on demand** (the side / back of an ornament only seen in 3/4, a picture full of reflections):
`lune run kit vision angle <picture> --azimuth 90 --elevation 0` (the same object from another camera) and
`lune run kit vision edit <picture> --prompt "remove reflections, flat even studio light, white background"`
(Qwen-Image-Edit-2511, offline; kit/gen/README.md). LOW TRUST: generated pictures — look at them to understand a
shape (or hand one to `kit gen`), never trace, measure or colour-match from them; check it is still the same object.
**Start from the IDEA, not one name:** `lune run kit refs expand "<idea>" [--also "names you know"]` -> the real
objects of that kind and their families (Wikidata: the idea's words, what each is based on, the other models based on
the same thing), the sizes Wikidata has (unchecked: confirm with a second source) and how many licensed 3D models
each has on Sketchfab (titles that name it). A suppressed pistol idea -> Welrod, B&T VP9, Type 64, QSW-06, HDM...;
an AMT Hardballer -> the M1911 family. Gather references for the close ones, not only the exact object.
**Real DIMENSIONS with their sources:** `lune run kit refs dims find "<object> <part>"` (kit/real_specs) — import
them: `kit refs dims wikipedia "<page>"` (a weapon's length / barrel / weight, a cartridge's SAAMI sizes), `kit refs
dims wikidata "<name>"`, `kit refs dims model refs/<name>.inspect.json --object "<name>"` (a dissected model's parts:
trust LOW), `kit refs dims fasteners` (ISO 4762 screws, ISO 273 clearance holes), or `kit refs dims add ... --source
<url>` (a drawing, a manual: trust high). Two sources more than 3% apart are flagged: find a third. A part answered by
a measurement cites its row: `ref: dims:<id>`. Build a size from the highest-trust row, never from memory.
**Reference MODELS (every side, every cross-section — what no photo gives):** `lune run kit library find "<object>"`
(Sketchfab's CC library: no account to search; pick a REAL make, the most faces) → `kit library get <uid>` (needs the
owner's SKETCHFAB_API_TOKEN in the environment — never ask for it in chat) or `kit library get --url <.glb|.zip>
--license cc0 --title "..."` (Smithsonian 3D scans, no account) → `kit refs measure <model> --name <name> --length-mm
<real length>` (a library model is rarely at real scale): sizes, loft sections with their squareness (a grip that WRAPS:
`a.loft(stations)`), side / front / top outlines with no camera error. Downloads are vetted by the tool (glTF only,
header + path checks, safe unzip, size caps, CC0 / BY / BY-SA only, licence recorded); library models are references,
never shipped. A staged model's backdrop and loose tools are left out, an animated one is measured assembled; LOOK at
`build/refs/<name>_side_mask.png`: the front must point RIGHT (else `--front min`).
**Then LOOK INSIDE it — not only its outside:** `kit library inspect <uid> --name <name> --length-mm <real length>
[--front min] [--part <words>]` → every part ALONE (`build/library/<name>/parts_sheet.png`: its own size along its own
axes, kind, the openings you can see through it in mm, its material colour / metal / roughness), what touches what,
an assembly animation's take-apart order and each part's way out (relative to the frame), an exploded view, and
`--part safety` = that part from its own side, top, front and 3/4 on a 10 mm grid (a part reference to trace and build
FROM). Read `refs/<name>.inspect.json`: per part it also DISSECTS what the part is made of — `edges` (sharp edges,
bevels measured as the CAD size: chamfer offset / fillet radius, the bevelled share), `surface` (how it was made: cad /
smooth / sculpt_or_scan / faceted), `uv_layout` (islands, seams on hard edges, texture px/mm, stretch, mirroring),
`baked_detail` (what its normal map carries: strength, a repeating pattern's pitch in mm, the relief in mm and its
height picture in `build/library/<name>/detail/` — the sculpt a game model keeps in its textures), `colour_wear`
(colour, roughness / metal ranges, edge wear and grime measured by distance to outward / inward edges). Those numbers
are what real models DO: copy the habits (bevel sizes, seam placement, texture density), not the meshes. A model's
numbers can be stylised (a game model's checkering enlarged): a published dimension outranks them.
**Then LEARN from it:** `kit learn <name> --category firearm [--roles "Trigger1=hammer"]` adds the dissection to the
kit's knowledge (`kit/learned/<category>.json`: every metric per part role and per finish, as low / typical / high
over the models, each model counting once). `kit learned show firearm` reads it; in a build, `rbx.learned("firearm",
"bevel_size_mm", "role:slide")` gives the typical real value; `kit library inspect build/models/<asset>.blend --name
<asset>_build --length-mm <real length> --out refs/private` + `kit learned compare <asset>_build --category firearm`
lists where YOUR build differs from what 2+ real models agree on (UV seams off hard edges, a too-strong normal map,
too few texture pixels, a pattern at the wrong pitch, edges darker than flats...) — the biggest gap first, with what
to do. A private build's inspection stays in refs/private. The author's part NAMES can be wrong (a 1911 model's "Trigger1" was its
hammer): trust the tile, not the name. And a library model is its author's reading of the object: cross-check a size
that matters against a published dimension before building from it.
`lune run kit trace <image> --name x --box ...`
-> an outline traced from a reference view (extrude it instead of typing coordinates).
`lune run kit vision edges|cutout|depth <photo>` / `mask <photo> --point x,y` -> build/vision/: the photo's lines (what
to model INSIDE the outline), the object alone, one part's mask, relative depth (where a form bulges) — local models,
offline, checked against their pins (`kit vision doctor`).
