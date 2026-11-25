---
name: parallax-3d
description: Make realistic, game-ready 3D models for Roblox (weapons, props, vehicles, creatures, building pieces) with the kit — ONE planned pass through 10 stages (brief, gather every reference, a model sheet the owner approves, a generated 3D draft, a blockout the owner approves, shape, surface, mechanism, look and judge, present) using the whole arsenal: picture search, 3D reference models and sourced sizes; local AI generators and vision models; CAD for machined parts; scanned materials, engraving, decals, relief; auto-fitting of proportions; take-apart mechanisms; a verifier and the owner's verdict. `lune run kit plan <name>` shows where an asset is and the next stage's commands. Use for any modeling task.
---

# parallax-3d — the route card (the detail is in `reference/`; the record is in `kit/knowledge/vault/3d/`)

Start: `lune run kit status --dept 3d` (the golden set, the graveyard, the owner's last verdicts), then
`lune run kit plan <name>` — it prints the stage you are in and its ≤ 5 commands; `kit help --stage 3d:<stage>` too.
Props: `lune run kit make <name> "<object>" --tier prop` runs the whole pipeline inside the budget (~6 min).
A `complex` / `hero` make STOPS twice for the owner (2026-11-17): after the references it draws the model sheet and
waits for his yes before any generator; after the fit it draws the blockout and waits before the bake. Show him
the picture it names, record his words (`kit approve 3d <name> "<words>" --by owner --stage sheet|blockout`), run
`kit make` again: it goes on past an approved stop (`kit make-gate <name> sheet|blockout` asks the same question).

## The owner's rules (every one has a date and a verdict behind it)
1. Budgets are HARD: prop 10 min, complex 30, hero 60 — of build time per attempt; the kit's clock decides: past it
   `kit asset` / `kit optimize` build NOTHING (rework included: the rim's ran 26 builds on a 10-minute clock) — they
   list what to show the owner and the piece's open cards; only his words reopen it (`kit plan <name> --extend <min>
   "<his words>"`, or `--restart "<his words>"`: a new attempt). `kit watch` and `kit fit` ask the same before every
   rebuild; `kit asset all` (a maintenance rebuild of every piece) reads no clock. The tier is the one the attempt
   started on (editing the brief never lifts a STOP). A piece with no clock starts one at its first build; an attempt
   that ran out before 2026-11-10 16:11 got one fresh attempt at its next build.
2. Gates are not quality: the Glock went 49 -> 51.5 in 10 h of green checks. Never report a score, an IoU or a green
   gate as progress on the look; LOOK at `build/renders/<name>.png` beside the reference after every milestone.
3. References first, PER PART, then build FROM the data (pictures ≥ 2 px/mm per hero feature; two reference MODELS
   checked for QUALITY — mess, holes, scan noise, a lying label; patents; the maker's turntable; sourced sizes).
4. One planned pass, never a rebuild loop; "DON'T LOOP WITH BS CAD": CAD is one route among many, time-boxed.
5. Our own unapproved builds are not reuse material; private designs are never committed or uploaded.
6. A study's lesson answers hold for the ROUTE they were written for (the rim's round 5 learned baked bevels make a
   sawtooth, then its S1 baked every fillet). Flip a switch that moves detail between geometry and maps — the game
   version (`low=True`, which bakes no shader round unless `edge_radius=` asks one), parts on the high only
   (`low=False`), rounds baked (`low={"round": 0}`), `edge_radius=0` —
   and `kit asset` / `kit optimize` refuse until `kit study <name> --reroute` and every matched lesson (the route's own
   lessons rank in) is answered again for it; a copied answer does not count. The change alone never turns kit verify
   red (after `--reroute` the study owes its new answers like any study: answer them at once).
7. A hero's tier is its BRIEF's, and a hand-written hero is judged, not refused (2026-11-11: "Yes, turn them on",
   "Yes, allow them"): a script with no `quality=` builds at `- quality:` in `<name>.brief.md`; a hero / aaa script
   kit make did not write builds and must pass EVERY hero check with no waiver (what it declares off fails it). His
   7+ / keep pieces unchanged since he judged them build as before (`board/grandfathered.json`, by sha1).
8. LOOK at every round at the size he judges at (2026-11-11, "Yes, lift it": this lane has no image cap). A build's
   summary ends with `LOOK: <folder>`: six views at 1024 px or more and, for each hero feature of the brief that names
   a box in a traced picture, a PAIR `f_<n>_<feature>.png` — the reference's box first, then the model's SAME box
   from that picture's camera, 1024 px on its larger side (a wolf head that was 40 px of a 512 px view). Open every
   pair; a hero feature with no close-up is named with its reason (no picture, no box, a picture that is not a traced
   view): fix the brief, not the build. A shape round (`kit asset <name> --geo`) keeps the same pictures in
   `build/judge/<name>/geo/` within seconds: never shape for rounds on numbers alone. One part being shaped:
   `kit asset <name> --geo --only <part words>` - those parts alone, the whole model's checks said as warnings
   (2026-11-17); run a full `--geo` round before calling the shape done. The take-apart / line-art views
   are asked for (`kit asset <name> --schematic`), no longer rendered by every build (they cost one hero 17 of its
   20 minutes on a round that changed its colour).
9. TWO cheap things he approves before a new complex / hero / aaa piece is detailed (2026-11-11: "A concept sheet we
   really need ... block[out] approval"): the MODEL SHEET (`kit sheet <name>`: the views, a large callout per hero
   feature, the palette — refused while a hero feature has no picture box, no size or under 2 px per mm) before any
   shape, and the BLOCKOUT (`kit blockout <name>`: the big shapes in clay against the sheet, seconds, no bake)
   before any detail or bake. His yes for each: `kit approve 3d <name> "<his words>" --by owner --stage sheet |
   blockout` - or his own click on `kit review <name>` (one page: the sheet, the blockout, the newest build's views,
   the finished piece, each with its state; the click runs that same command); it holds for what he saw (a changed
   sheet, a re-drawn blockout: his word again). `kit asset` refuses
   without them (`--geo` rounds need only the sheet's). LOOK at each page yourself before showing it.
   `reference/12-*`.
10. A sculpted / organic hero part is NEVER typed as shapes (2026-11-12, on seven rounds of typed feathers: "the
   tryouts look horrible ... try something new"; on the route below: "Wow, I'm actually kind of amazed" and "you
   have to get it correct from every angle"). PICTURE FIRST: redraw the reference's small crop large with the local
   image model (`kit vision plate --from <crop>`) and show him the picture; generate from that ONE picture (`kit
   gen`); check the SHAPE against every view the reference has, side by side, before any detail; then `kit sharpen
   <part.glb> --about "..."` (view after view: render, redraw that render sharp, project it back into the part's own
   colour map; `--fold` first lays a splayed pair of wings straight back); into the build at the reference's
   MEASURED size with its own maps (`a.import_mesh`, no `mat=`). Typed shapes are for machined parts.
   `reference/13-*`.

## The route (10 stages; `kit plan` locks each until the previous artifact exists)
| # | Stage | Its gate | Read |
|---|---|---|---|
| 0 | brief | what it is, tier = budget, what must WORK, whose design, the parts plan (a route per part) | `reference/03-*` |
| 1 | gather | dossier approved / a sourced size; coverage ≥ 2 px/mm; 2 reference models graded; every traced part LOOKED at (`kit refs crop`); then the STUDY (`kit study <name> --new`): each reference READ (silhouette, measured proportions, shape language, why it works, surface, weak), what all good ones share, OUR version (keep / change / signature / target numbers), each matched vault lesson applied or skipped with why. `kit asset` refuses a new asset without it | `reference/04-*` |
| 2 | sheet | a new complex / hero / aaa piece: the MODEL SHEET drawn with no problem (every hero feature: a picture box, a size, ≥ 2 px/mm) and APPROVED by the owner as it is now (`kit sheet`, `kit approve ... --stage sheet`); a prop: not needed | `reference/12-*` |
| 3 | draft | generators PER PART for organic parts only (never a hero's hard surface); `glb_topology` + `side_check` pass; the GPU idle | `reference/05-*` |
| 4 | blockout | the same pieces: the big shapes only, the BLOCKOUT sheet drawn from a shape round and its proportions APPROVED by the owner (`kit blockout`, `kit approve ... --stage blockout`); no detail, texture or bake before it | `reference/12-*` |
| 5 | shape | every traced view matched ≥ 0.9 (`a.trace_match`) or `a.not_reference(why)`, and a hero with NO traced view fails (`stage`: unmeasured); hero hard-surface: `kit refs sections` ≤ 1.5 mm vs a reference model; organic: a calibrated `a.form_match`; a NEW piece: every coded part made by the builder call its plan line names (`a.repeat` / `a.scatter` for many alike, `a.sweep` / `a.taper` + `a.bend` for long curved forms, `a.loop` / `a.inset` / `a.push` / `a.smooth` for one moulded body), nothing alike typed one by one (`methods`: "Which method for which part") | `reference/06-*` |
| 6 | surface | a look per material with its source; markings ENGRAVED at measured places; a wear preset (`life=`); `dark_finishes` clean; texel ≥ 5 on high-contrast detail | `reference/07-*` |
| 7 | mechanism | hero only, after the look passed the owner: `a.joint` travel without collision; `a.cycle` - the action RUNS on the .blend's timeline, every joint posed together (`mechanism_cycle`); `a.disassembly` runs | `reference/08-*` |
| 8 | judge | the verifier: same crop of reference and render per view, ONE edit; ≤ 10 rounds then the OWNER (`kit verdict asset`) | `reference/09-*` |
| 9 | ship | a game version (`kit optimize`) that spawns in Studio; public assets uploaded; `kit promote` only on an owner verdict ≥ 7 | `reference/10-*` |

Route per part family (the graveyard forbids the rest; `kit/knowledge/vault/3d/routes.md` is what `kit plan` enforces):
machined / hard-surface -> CAD from mm profiles (`a.cad`, `rbx.profile`, `kit cad check` in seconds) + sections vs a
reference model · organic ornament -> a checked reference mesh as clay (`s.add_part`, `a.form_match`) or a per-part
generator draft + relief · cloth -> `rbx_garment` drape · thin plates / rims -> `s.strap` · props -> `kit make` ·
a designed / fictional object with a checked reference model -> `kit refs outline <model> --name N` (each reference
part's outline in mm + its thickness -> `a.cad` extrudes it, edges rounded: the ODM swords 4 -> 9/10) · a round part
of a reference model -> its measured revolve profile. Judge DETAIL where it shows: `kit look closeup <asset> --part
<name>` (hero distance, Cycles) — never on the whole-asset sheet, where a blade's lines are a few pixels — and its
materials under four lights + a clay pass: `kit look lookdev <asset>` (with the 30-240 sRGB albedo check). Tertiary
detail: what the light only grazes is STAMPED into the normal map, no triangles (`a.stamp(kind, at, size, facing)`:
rivets, screws, bolts, vent, panel_line, grille, knurl, weld, stitches, socket, treadplate, louver, hinge, rib,
hammered, nameplate, and the ornament reliefs rope, fluting, milgrain, scales (shape="pointed": a dragon's), scroll
(a running Vitruvian wave) — recesses darkened like AO (never hammered's open dimples); a stamp finer than its
map can show is named by the `stamp_texels` warning — preview: `kit asset stamp_library`); a DRAWN ornament
(scrollwork, filigree, a crest, an engraved line) from its own picture is `a.ornament(<.svg | .png | .npy>, at,
width=, facing=, depth_mm=, profile="round" | "v" | "flat", cut=)` — the same normal-map route, its edge from the
exact distance to the drawing's border, its thinnest stroke held to the same 2.5 texels (`around=` wraps it
round a round part); a MOULDING round a frame or a rim is `a.moulding(name, profile, "<Part>", mat, facing=)`
(mitred corners; laid into a trim sheet it runs the band by its own length); parts poured as one are
`a.cast(name, [parts], mat, fillet_mm=)` (a true fillet where they meet: CAD-fused when they are a.cad parts); what sticks out
in silhouette is geometry (`rbx_parts`: `P.rivets(..., sunk=0.4)`, `P.weld`, `P.rivet_ring` — preview: `kit asset
detail_library`). Wear follows USE: `a.contact("hand" | "rub" | "ground" | "drip", part="GripL")` (the box from the
part: drip = rust-and-grime streaks running down from a fitting); dust on what faces up: `a.material(..., dust=0.5)`.
A game design with no model of it but the game's own orthographic renders (Scarborough Fair 9/10): trace the side
view into parts, take widths from the top view and every SECTION from the front view + the side view's ridge lines
(two round tubes touching, not a block); trace gold / coloured trim and the logo by colour (`kit refs inlays <view>
--hue 34-72 --trace <trace.json> --length-mm L`) and WRAP it onto curved parts (`cad_parts.inlay(shape, host)` in
a.cad); hang chains with `P.hanging_chain` (every link threaded); ornate screws: `P.slotted_screws`; judge the left
side with `kit look closeup <asset> --part .. --view three-quarter-left`. A game gun's edges are SOFT: when fillets
refuse a traced / fitted outline, round it on the mesh — `a.cad(..., round_mm=<~15% of the part's thickness>)`.
Small parts get their own trace: `kit refs detail <view> --box .. --name .. (--hue | --dark | --point x,y --neg x,y)`
(4x upscaled, 1/4 px); jewel settings, collars, medallions: `cad_parts.ring(r_in, r_out, h, round=1)` (never a flat
disc); gold trim as a bead (round_mm ~0.75 of its height).
**EVERY EDGE FROM THE REFERENCE (the owner, 2026-10-22: "details ... I mean the edges etc too, everything on anything
we ever work on").** Edges are details on every part of every asset: measure the art's rounds before building —
`kit refs edges <picture> --name <asset> --trace <t> --length-mm L --parts <parts.json>` (the ramp across each edge,
calibrated on Blender slabs: a radius per part, +-0.5-0.8 mm) — and set each a.cad part's `round_mm` / `edge_roles`
from it (the `cad_edges` gate warns on any CAD part whose edges were never decided). ROUND IN CAD, NOT ON THE MESH:
`a.cad(..., fillet_mm=<the art's round>)` fillets every hard edge in the solid (silhouette included) — the asked
radius where it fits, each edge's own largest radius where not, crash-safe (a child process with checkpoints) — and
it needs the outline redrawn TANGENT (`redraw(pts)` / `"redraw": True`: lines + arcs meeting smoothly where the art is
smooth; OpenCASCADE refused 30 of the hammer's edges at 1 mm on the old kinked redraw, none after). `round_mm` (mesh
bevel) is the fallback: dense CAD tessellation folds a mesh bevel past ~0.3 mm; shaded rounds stay <= 0.8 mm (wider
read MELTED). After a build: `kit look edges <asset> --part <word> --picture <p> --trace <t> --length-mm L` measures
EVERY build part's edges against the art (the parts' ids rendered with the same camera; `--parts <file>` for traced
regions instead) and writes each part's next round. Measure, set, rebuild, measure once more, then LOOK at a close-up.
**ORIGINAL PIECES: DIRECT, THEN BUILD (the owner, 2026-10-25: "work on originality ... a creative director and
creative direction in the pipeline").** An original is decided before it is modelled: `kit design direction <Piece>
--new` (intent, one idea, 6+ references across media, 3 pillars, bans, 3 directions 2+ axes apart, each with a `Draw:`
line — the director's words for the picture, never the poetic idea: "a living flame" drew muzzle flashes), the
MAKER's language (`kit design maker <Maker>`: shape family, motif, edge rule, materials, detail share, bans; two makers
2+ rules apart; `a.maker()` in the build), `kit design explore <Piece>` (side concepts per direction, readable at 32
px, original vs our past pieces, bans screened, a quality-diversity grid -> the pick board), the pick recorded in the
doc, `kit design concept <Piece> --from <pick>` (the clean side view the route traces; generated turned views are
unreliable: thicknesses come from the director's section plan), the build, then `kit design review <Piece> --asset
<name>` (one fix list, one round, then the owner; it measures the build against the PICK's concept view in the view the
doc names, `View: side|front|top`). Pieces: games/SampleRegion lantern_pistol, tide_shield (designed from its front),
lantern_hook. BUILD FROM THE CONCEPT'S DATA: measure its side row by row (a pole's half-widths, a lantern's profile, a
crook's centreline by rays) into `<piece>_side.profiles.json`, then `turned(top, back)` for anything round (a
finely-sampled revolve is otherwise an INVALID solid), a sweep along the measured centreline for a bent tube (its
collars and caps their OWN parts: booleans onto a sweep come back broken). A set shares one finish; patina gets
`chip=0` (`under=` makes a finish "paint": its chips showed bright arcs a vision model called gold).
**SCULPTED, NOT SLABS (the owner, 2026-10-23: "the straightest edges ON human history ... do not confuse smooth
shading with smooth geometry").** A fillet on an extruded side profile is still a slab: flat faces, square shoulders.
Game-art plates (a frame, a grip, a hammer, a trigger, a housing) are INFLATED: `a.pillow(name, outline_mm, mat,
core=, h=, edge=, top=, holes=, side="both"|"+"|"-", plane="ZY", base=)` — each face rolls off the traced outline on
a quarter ellipse `edge` wide x `h` high and crowns `top` toward the middle (a part thinner than 2 x edge gets a round
top), the silhouette exactly the outline, always closed (kit/blender/rbx_pillow.py: height from the distance to the
outline — CAD offsets + lofts split on traced thin spots). Round / lobed housings in CAD: `dome(lobed(r, n, depth),
h, edge)`. A gold rim is a ring pillow (the outline grown, the part's own outline its hole), never a plate. CHECK the
form, not the shading: `kit look silhouette <asset> --part <word> --picture <turnaround> --box <the view's box>
--view front|back|top|bottom` (the build scaled by the one axis it has right, widths per row in mm, an overlay) for
every view the sheet has, then `kit look closeup --view three-quarter` / `three-quarter-left` of each part.
**DETAILS FIRST, MEASURED (2026-10-22, the detail pass).** Before modelling, list EVERY small detail of each picture:
`kit refs inventory <picture> --name <asset> --what "<object>" --trace <t> --length-mm L --parts "hammer,trigger,
screw" --masks` (a local VLM lists + boxes the details, SAM 3 finds the named parts; each graded ok / upscale /
close-up by its pixels: the SHOT LIST in `<asset>.details.json`; a close-up row = find a sharper picture first; a
video turntable / inspect: `kit refs frames <video> --name ..`). Its boxes are MEASUREMENTS: on Scarborough Fair they
put three screws, the jewel and the crest 5-40 mm from where the 9/10 build had them — place + size details from the
inventory (VLM and SAM 3 agreeing), never by eye. Redraw traced outlines as a designer draws them: `kit refs redraw
<x.detail.json>` (true lines + arcs, equal radii, `--mirror x,0` for symmetric parts) and build with
`redraw(pts)` / `prims_face(prims)` in a.cad (they fillet where fitted splines refuse). Raised trim: `kit refs inlays
.. --centrelines` -> `cad_parts.bead(path, width, height)` (a swept half-round, round ends); a stone sits in
`cad_parts.setting(stone_d, ...)` (seat + lip); `P.gem(..., ior="sapphire")` refracts in the showcase. Edges by ROLE:
`a.cad(..., round_mm=2, edge_roles=[{"box": (..mm..), "round_mm": 0}])` (cut edges crisp, the rest soft); soft-hard
parts (a grip, a hammer, a game frame): `a.cage(name, outline_mm, depth_mm, mat, soft=1.5)` (quad cage + holding loops
+ subdivision). Engraved text: `kit refs read <pic> --box ..` then `kit refs font <pic> "<text>" --box ..` and
`a.text(..., font=<path>)`. CHECK details, not the silhouette: `kit look details <asset> --part <word>` (each detail
beside the reference's, worst first: it found a mint gem where the art has olive, an empty crest ring, a twisted
chain built as beads) and `kit look zebra <asset> --part <word>` (wavy inlays break the stripes). Small parts for the
game version: `with a.floaters():` (baked into the host's maps).
**GAME MESHES: HIGH AND LOW (2026-11-09, the 3D crafts plan S1, board card macm).** `rbx.Asset(..., low=True)`: every
`a.cad` part is made twice — its HIGH as written (fillets, rounds, fine facets) and a LOW from the same code with
`P["low"]` set (the kit's `rounded(prof, r)` rounds the low's corners over 30 degrees in steps of 24 at most, its
points at equal turns — `low_turn=60`: right angles only; the high's at 6 degrees; a part with `fillet_mm` of 0.8 or more gets
mesh rounds on its low's edges over 45 degrees where there is room, ONE width per chain of edges), 0.5 mm facets —
and the high is baked into the low (normal, colour, roughness, metal; bake GROUPS: each part only
from its own high, so joints never trade normals). `a.cad(..., low=False)`: a part of the high only (threads,
lettering, casting marks), baked, never in the game mesh. Facts `low`: triangles against the budget (prop 5,500 — the
build fails over it), each group's silhouette (p95 within 0.5 mm of its high), RenderFidelity; `<name>_high.blend`
is saved beside the build and `game_fidelity` holds the low to it. The car rim: 17,096 -> 5,098 triangles, its
threads and fillets in the normal map; its crevice shadow measured over the texels the bake wrote (facts
`low.<group>.occlusion`). Parts that change a part after a.cad (cut, fuse, zone, remove) refuse a high-and-low part: do it
in its CAD code. Every full build's .blend opens in the owner's own view (Material Preview, forest HDRI) and carries two
more scenes, "Roblox look - day" / "- as read" (his place's Lighting, `kit/blender/roblox_looks.json`): the Scene list,
then Z -> Rendered. `kit look sheet <asset>` = his view, the Roblox look, clay, wireframe, texel checker and every
texture set's maps (`<asset>_sheet.png`; `<asset>_sheet.json` records which build it looked at).
**UVS BY PART (2026-11-10, the 3D crafts plan S2).** On the high-and-low route the game mesh is unwrapped by what each
part IS (`kit/blender/rbx_uvparts.py`), not by a smart projection: seams on its hard edges (over 35 degrees: the low's
own smoothing angle) and where a strip, ring or band is cut open; a TURNED band (a lathe's cylinder, cone or narrow
ring) laid as straight strips (one too wide in radius cut at its best ring; a chamfered lathe body that closes on
itself opened at its sharpest edges); flat faces as they lie; a face with tubes hanging from it cut where they leave
it; an island the unwrap still crushes is projected. IDENTICAL parts share ONE place: the bake writes the original and
the copies share its texels (never on an asset with a stamp, a contact, a projection or a texture_from). Make them by
TURNING one part (`a.cad(..., rot=(0, 0, k * 72))`), never by turning inside the CAD code: each angle is then meshed
and rounded its own way and only some come out alike. A copy is cut into the same triangles as its original
(`triangulate_like`) and every pair is checked again on the triangles (`keep_copies`; facts `copies_dropped`): BEAUTY
alone flipped a turned spoke's diagonals, its corners were laid from other islands — a striped blotch. Density by what
is seen is the builder's word only: `a.texel("<part>", factor)` (a barrel under its tyre: 0.5; a dial seen close: 2) —
nothing is shrunk automatically (that blurred the rim's threads to blobs). The strips are cut four ways, ranked by the
box packer, and the best two packed by shape. Facts `uv_parts.<group>`: map use (copies once), strips / flat /
stacked, texels per mm per part. A part can bring its own UVs (`a.mesh(..., uvs=)`): `rbx_parts.thread(...)` is a
real, light screw thread (an ISO ridge: 482 triangles for 10 mm of M14 at its 12 facets a turn — keep a turned
detail's facets at 30 degrees or under: at 36 each shaded hard; a fine twin baked onto it as a floater). The car rim
(S1 -> now): maps 28 / 14 / 60% used -> 80 / 70 / 42%; barrel 0.70 -> 1.16 texels per mm, lip 1.24 -> 2.73, face
1.90 -> 2.30 (the face map holds 438 islands: the hub's mid-poly rounds and lug holes make hundreds of small ones).

**THE GAME VERSION UP CLOSE (rework 6ebz, 2026-11-10: the owner's "Yes, fix it first" on wavy and sawtooth edges, a
bright slit, painted threads).** Find a fault by rendering the close-up three ways (as built / normal map unlinked /
colour flat) and counting the normal map's texels by tilt; then fix the ROUTE, never one asset. What the high-and-low
route does for every game version: the HIGH shades with its solid's own B-rep normals (cad_run exports them; meshed to
0.1 mm / 6 degrees at least) — guessed normals swung on long fillet triangles and the bake copied the waves; a round
that shows is GEOMETRY on the low (above) — baked into a 1-3 texel/mm map, a 1.5 mm round was a 2-5 texel band that
stair-stepped; mesh rounds are cut one width per CHAIN of edges (bevelled at different widths in separate passes, the
rim spoke's arm and flare left a crease the whole arm long: the bright slit at the lip); a part bakes a flat normal map
(facts `low.<group>.flat_parts`: its near-flat corrections only drew lines along the seams) only when its low is
mid-poly (rounds as geometry), within 0.35 mm of its high, hosts no floater and every hard low edge is hard on the high
too — a faceted or sharp low keeps its map; the cage reaches past the largest gap (1.2 x the silhouette's max, 1 mm to
2.5 mm); AO at 128 samples; a texel tilted past ~72 degrees — a ray that fell into a hole past the low's polygon and
hit its wall: a glint by the rim's valve hole — takes its neighbours' mean (`low.<group>.normal_texels_calmed`); a
high whose mesh is bevelled (`round_mm`, `edge_roles`, a refused fillet) shades by its mesh, and a mirror twin gets
its B-rep normals mirrored. A revolve's game mesh finer round the axis takes an ANGLE limit (`low={"angle": 6}`), never
a finer tolerance: at 0.3 mm OpenCASCADE meshed the thin bands of the rim lip's rounds with different counts round the
axis, and the fans of twisted triangles between them creased the shading. The car rim: 20,556 triangles (S1 5,098;
round 5's real geometry 55,304): real threads at 20 facets a turn, 30-sided lug holes (`low={"angle": 12}` on the hub)
and a 60-sided lip, for the owner's close-ups 3 cm from a hole. `game_fidelity` judges the game version UP CLOSE too
(S1 passed its 512 px numbers with all four faults — every one a pixel or less): the same 6 cameras at 2048 px, the
shading normal and the DEPTH along the camera, in 32 px windows; more than 3 fault windows fail the high-and-low route
— shading parted > 10 degrees over 8% of a window, or shape the low lacks or adds over 20% (its surface > 0.6 mm off
the high's, a hole capped flat, a surface only one has: detail only painted on). LOOK at its crops:
`build/renders/<name>.fidelity/close/`. S1 is the selftest's bad example: 510 fault windows (the first rework pass,
the striped one, 621; the final rim 2).

## What never worked (do not retry without the owner's words — `kit/knowledge/vault/3d/graveyard.md`)
An extruded side profile + boxes for a hero (caps ~50) · a whole-object generator for a hero's hard surface (0-8/10)
· organic form typed as SDF primitives (28-39; a reference mesh reached 75) · a lit render projected as colour ·
detail the real object lacks, added to move a score (owner 1/100) · a tournament weighted on crispness · internals
before the exterior looks right · a coat hung from the waist.

## Traps that cost a day each (the full list: `lune run kit lessons 3d`)
Coplanar faces are the #1 boolean failure (overshoot cutters; inset mating outlines ~0.15 mm) · OpenCASCADE refuses
fillets over traced perimeters (round only the edges that read; corner_deg=1 on machined parts) · `cad_solid` open
edges while `cad check` says 0 = volume_untrue (bisect by mesh_volume_error) · a turnaround's small views can be
MIRRORED (flip the picture, never the model) · one global IoU hides a wrong region (local windows) · the bake colour
buffer is sRGB · scans are box-projected (never wire NormalGL) · dense sculpts unwrapped by form · a keep-trim is a
prism (min_mm=4) · `a.cad` params ride the command line (32k) · a SAM click read off a resized grid lands on the
backdrop · Hunyuan faces +Z · `kit grade` / `accept --lower` need the OWNER's keystrokes · one GPU job at a time.

## Read next
`reference/01-start-here-*.md` (kit make) · `reference/02-the-pipeline-at-a-glance.md` (rules of the pass, stack
per part) · `reference/11-gates-*.md` (every check) · `reference/13-organic-parts-picture-first.md` (a wolf, a wing, a
beast: never typed) · `reference/14-what-a-finished-surface-needs.md` (how sharp is sharp enough, the map's size from
the need, the order a surface is made in: research 2026-11-12) · `kit/knowledge/vault/3d/index.md` · `[[shared/vision-stack]]`,
`[[shared/reference-tools]]`, `[[shared/gpu-rules]]` in the vault · `MODEL3D_AUDIT.md` §13 (the root causes).
