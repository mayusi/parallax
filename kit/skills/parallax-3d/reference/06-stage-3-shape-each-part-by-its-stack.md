<!-- reference for the parallax-3d route card; verbatim from the skill page (2026-10-16) -->

## Stage 5 — Shape: each part by its stack

### Which method for which part (THE METHODS LOCK - the owner, 2026-11-13: "enforced in the terms of being used")
A part made in code is made by the method that FITS it, and its parts plan line says which, as the builder call:

| The part is ... | Make it with | Never |
|---|---|---|
| many alike in a row, a ring, along a line, a grid (teeth, spokes, links, slats, fins, treads) | ONE inside `with a.repeat(...)` (`step=`, `around=`, `along=`) | typed one by one |
| alike at uneven places (screws, feet, pegs) | ONE inside `with a.repeat(at=[places])` (the first place is where the part is modelled), or `a.mirror` for a pair or four | typed one by one |
| many spread over a surface (scales, shingles, rivets, barnacles, studs) | ONE inside `with a.scatter(onto, ...)`; `a.stamp` / relief when it only has to READ | typed, or left out |
| long and curved (a horn, a hook, a cable, a rail, a strap, a tail) | `a.sweep`, or built straight then `a.taper` / `a.twist` / `a.bend`; `a.conform` to lay it on a body | a box, hand-placed loft stations |
| a boxy body with panels, pockets, bosses (a crate, a case, a console) | ONE `a.box(bevel=0)` cut with `a.loop` / `a.inset` / `a.push`, then `a.round` | separate boxes stacked |
| a soft or moulded form (a pod, a helmet, a cushion, a pebble) | that cut box, then `a.smooth` with the edges that must stay held | bevelled boxes |
| machined, with exact rounds, holes and threads | `a.cad` | boxes with cuts |
| a surface with no thickness (a leaf, a banner, a cloth's hem, a hair card, a grille's sheet) | ONE sheet of faces (`a.mesh`, bent with `a.bend`), then `a.two_sided` | a thin box per leaf; a sheet left open |
| an outline or holes too fine to model (a leaf's edge, a grille's bars, chain-link, torn paper, lace) | a plain sheet, `a.two_sided`, then `a.cutout` (a picture, or a rule on the point) | hundreds of tiny faces; a solid plate |
| sculpted, figured, organic | not code alone: `a.sculpt`, generated, relief (the stack table) | boxes |

`kit plan` holds a NEW piece's brief until every part made in code names its call(s) (`... | code: a.box, a.loop +
a.inset for the lid | ...`; a line that names a builder call IS code, whatever route word it uses). A part whose
own noun says "many alike" (`Teeth x12`, `Window bars`, `Ring of rivets`: a count of three or more, a plural the
kit knows, "a row / ring / grid of") needs a repeat / scatter / stamp (a mirror for a pair or four); one whose own
noun is long and curved (`Lanyard hook`, not `Hook plate`) needs a sweep / deform / loft / tube. The BUILD is then
held to the plan, from its own record of what it did (the `methods` check, an error):
- a method the plan names is used - on as many parts as name it (three lines that say `a.repeat` need three
  repeated parts: one token repeat covers nothing), and for as many pieces as the line says (`Teeth x12` by
  `a.repeat` needs a repeat that makes twelve);
- four or more parts of ONE shape made one by one are refused, wherever they were typed (inside a repeat block
  too), whatever their material or a hair of difference in size, and when `a.fuse` absorbed them afterwards.
A blockout round is not asked (it is boxes on purpose). The lock holds pieces made AFTER it was switched on: the
build scripts that existed then are listed once (`board/locks.json` grandfathered `3d-methods`; in this repo
2026-11-13, in another project the first `kit new asset` / `kit plan` / `kit asset` run with this kit). Only the
owner waives it for one piece (`kit approve 3d <name> "<his words>" --by owner --waive methods`).

(A new complex / hero / aaa piece reaches this stage with its BLOCKOUT approved by the owner — stage 4, `kit
blockout`, `reference/12-*`: the proportions are settled; this stage adds the detail on them.)
Each part is made the way the parts plan says (the stack table above) from the data stage 1 gathered — never from
memory. Iterate a CAD part in seconds: `lune run kit cad check <name> --only <Part> [--look]` (no Blender); the
whole model's checks with `lune run kit watch <name> --geo` (a persistent Blender, no bake: seconds on a light asset,
minutes on a CAD-heavy hero — at milestones there); let `kit fit` move the `a.param()` proportions to the traced views
(on a slow build only the few that matter: `--only a,b --evals 24`). A full build only at the stage's end.
**Outlines in code: `g = rbx.profile`** (in a.cad code: `profile`) — `clip_h` / `clip_f` (a traced outline cut to a
part's range), `span_at` / `vspan`, `edge` (a measured edge's MEDIAN: the trace's pixel noise averaged out), `simplify`,
`between`, `rotate` / `shift`, `catmull` (a measured section swept through its keys with no crease — each polyline key
reads as a hard edge), `smooth_run` (a traced strap without its pixel wiggle; join it where the trace is straight: a
kink made a solid whose mesh disagreed with it), `u_floor` / `u_section` (a channel or trough with a half-ellipse
floor). **A part can match every view and still be the wrong shape inside** — the Glock's frame was solid where the
real one is a U-shell: `kit refs sections <name> --ref <library id>` cuts the build beside its reference model, and
`kit plan` asks for it on a hero with a reference model. `kit cad check` FAILS a part whose mesh does not hold its
solid's own volume (`volume_untrue`: it tears open on import while looking closed).
**From the gathered data to the shape** — the real-object list of stage 1 continues here (its steps 4-6; (c)-(e)
carry on its hero discipline (a)-(b)):
**Order of work: silhouette first.** Blockout (the outline, primary forms) → secondary forms → detail. While any
traced view (`a.trace_match`) is below its bar, a hero / aaa build is a BLOCKOUT: it FAILS on `stage` with one next
step — "silhouette first: side IoU 0.81 < 0.9 — fix the outline before detail work" — and the detail-level problems
(part review, texel density, colour, palette, quality score, internal lines, ...) are reported as deferred, not piled
on. The stage is measured, never declared; `Asset(stage_gate=True)` turns it on for a prop, `False` off (`declared`).
A hero / aaa build with NO traced view registered and measured FAILS on `stage` as well — "unmeasured: no traced
view registered" — and holds nothing back (the owner, 2026-11-12: "Yes, make it fail"). Its outline is measured
against nothing: the Gjallarhorn's build never registered one, and its lower rear stayed misread for 7 rounds (the
stock's thumbhole built as a trigger guard with a pistol grip behind it). Trace the reference's side view FIRST:
`lune run kit trace <picture> --name <asset>_side --front left|right` (`--cutout` for a pale object or a photo: a
plain trace takes ivory for backdrop), look at its preview; a hero build matches
`assets/models/<asset>_<view>.trace.json` by itself.
4. Model from the trace: `rbx_trace.region(outline, u0, u1, h0, h1, length_mm=L, holes=t.holes)` (clean pieces, never
   the bridges `clip` leaves on concave outlines; without `holes=` the trace's openings are FILLED — a guard opening
   came back solid and buried the trigger), `T.hull(hole)` for an opening traced around something solid, `T.clean`.
   `a.trace_match("<trace>", ignore=(groups the trace excluded), dont_care=[boxes where the reference is unreliable])`
   — the side silhouette must reach IoU >= 0.9 (hero / aaa: until every traced view does, the `stage` gate holds the
   detail checks back — fix the outline first). Trace and match EVERY view you have (`view="front" | "back" | "top"`,
   one call each): each is also measured EDGE TO EDGE — warning `view_gaps_<view>` names the worst 3 places beyond
   3 mm or 2% of the view's size, in mm with `a.real_scale` ("front view: the model is 13 mm too wide at the right (top
   to bottom)", "the reference has 59 mm more at the top front"), per region with `regions=`; numbers in
   `facts.references[].gaps`, places in yellow on `build/renders/<name>_ref_<view>.png`. A top trace runs back -> front
   like a side view (the model is turned to it). Every build then also runs the INTERNAL LINES check (`lines_<view>`,
   below): the lines inside the outline must match the photo's too — with `a.real_scale(mm_per_stud)` it says where a
   missing line is in MILLIMETRES (from the back, from the bottom).
   (c) `lune run kit refs profiles <trace> --anchor <part> --length-mm <real length>` -> every part in mm in the
   build's own frame; build each part from it (a.cad: `clean_profile(r)` makes a traced outline machinable,
   `fillet_soft(edges, r)` takes the largest radius OpenCASCADE allows and says so). Measure big straight edges
   (`median` of the traced edge) instead of copying pixel noise; a feature no picture shows (an ear round a pin) is
   added and said so. A traced outline that will be ROUNDED: build it from polygons (booleans stay robust on flat
   walls), then `smooth_profile()` as the sketch's last step — each run between corners refit as one smooth curve, the
   corners kept (`add(outline(pts))` for a single outline) — not `clean_profile`: its arcs at every traced point, tighter
   than the fillet, refuse it (the Glock frame: every edge refused, even alone). A part made of several widths (a
   frame: grip, receiver, guard) is ONE solid: the smoothed profile extruded once, intersected with a width ENVELOPE
   (the grip's loft + flat blocks) — joined as bodies, their curved walls coincide along the profile and the join lost
   7.7 cm3, or (fuzzy) dropped the whole trigger guard. A piece that must be rounded on its own is its own body with
   its outline INSET ~0.15 mm (no wall coincides), joined plainly; a CAD part that comes apart raises, never keeps the
   largest piece in silence. Extrude a body from its middle (`extrude(amount=w / 2, both=True)`: extruded one way, its
   far side's edges refused radii its near side took); round a body's long edges as ONE set (a set refused whole:
   test each edge alone, round the takers one by one); a corner rounded in plan tighter than the edge's fillet refuses
   it. a.cad's `tol` is millimetres off the true surface; each mesh is checked against its solid's volume. (d) `a.trace_match(<trace>, view="side_left" | "side", parts={"<traced>": ["<Model>", ...]})`:
   each part's own outline (IoU >= 0.85, edges within 1 mm or 4%) — the gate `part_match_<view>` FAILS hero / aaa.
   `pose={"Hammer": 30}` when the picture shows a moving part elsewhere (fit the angle on the picture, never move the
   rest pose to suit it); `"trigger!"` compares outlines only when its holes differ ON PURPOSE; `dont_care=` boxes
   (the design's own features the photo's gun lacks) are left out of the WHOLE-OUTLINE comparison and of the fit — a
   part listed in `parts=` is still compared whole, so leave out of `parts=` a part whose own shape differs on purpose.
   `align="<traced part>"` (a key of `parts=`): lay the model on the picture by THAT part instead of the whole
   outline's box — when one part sticks out differently in the picture (a cocked hammer, a longer beavertail, a game
   design's extra), the box fit shifts and scales every other part; align on a big part both show whole (a can, a
   barrel, a receiver). `a.project(<same trace>)` then paints with the same alignment. (e) Two
   references disagree (a real gun and the game's version of it)? The design's own picture rules its own features
   (sights, hammer, grip), the real object's photo everything else — written in the build's docstring, each
   `dont_care` / left-out part with its reason. Lay a design picture over the real photo first (best-fit offset and
   length: the Silverballer render lands on the Hardballer at IoU 0.92) — a guessed alignment shifts every part.
   **Part sizes in mm, every build:** `lune run kit refs views <name>` measures every traced part; a spec part with
   `"ref": "<traced part>"` is then set beside it (gate `ref_sizes`: what is SEEN of the part from the side — rays from
   both flanks — against the traced mask, frames lined up on all linked parts; off = more than 5% or 3 mm). Link only
   parts whose masks are CLEAN: a box prompt's SAM mask can fill the box or run into its neighbour (the Gjallarhorn's
   grip and guard were one area, its crown lost a claw) and `--part name=box` is the whole object inside the box.
   `kit refs views` carries kit trace's judgement into the views file; a ref to a doubtful mask is named by the
   `ref_sizes_doubtful` warning ("ref 'grip' is a doubtful mask: fills its box ... — retrace it").
5. A 3D reference at real scale (a CC0 scan, any glTF / FBX / OBJ): `lune run kit refs measure <model> --name x` ->
   `refs/x.measure.json` (size in mm, cross-sections) + side / front / top outlines with NO camera error
   (`assets/models/x_<view>.trace.json`). Build from them: `a.carve(side=..., top=..., front=...)` (three views: IoU
   >= 0.99 per view on a measured shape) or `a.loft("Body", rbx_trace.loft_stations(rbx_trace.measure("x"), L), mat)`
   (sections within 0.2%).
6. PROPORTIONS the references should decide are `a.param()` numbers — `L = a.param("barrel_length", 2.4, lo=1.8,
   hi=3.0)` — and `lune run kit fit <name>` moves them to match the asset's REFERENCES (silhouette IoU per view and
   proportions, CMA-ES over --geo builds in a persistent Blender) — never the quality score (a fit that chased it would
   buy clutter, not resemblance). `--write` keeps the values beside the script (`<name>.params.json`, used by every
   later build; `facts.params` lists them). A synthetic case comes back within 2% of its true values.

### The build calls
```python
a.material("frame", **rbx.finish("gunmetal_parkerized"), wear=0.2, chip=0.45, grime=0.4)  # a coating: chips show steel
a.extrude("Body", outline, depth, "frame", plane="side")   # (u, v) or (u, v, r): r rounds the corner
a.slab(name, outline, plane, at, thickness, mat, chamfer=0.01, direction=1)   # chamfered slab (plates/cutters)
a.text("Serial", "XV 331", pos, "decal", size=0.1, facing="+X", up="+Y", depth=0.01)   # raised lettering
a.cut(target, cutter) · a.mirror("X") · a.frame(pos, rot) · a.box/wedge/cylinder/sphere/loft/tube/mesh
with a.repeat(12, step=(0, 0, 0.3)): ...                   # everything made inside: a ROW of 12 (rbx_repeat)
with a.repeat(8, around="Y", centre=(0, 1, 0)): ...        # a RING of 8 (angle=120: an arc; rise=2: a spiral)
with a.repeat(20, along=[(x, y, z), ...]): ...             # ALONG A PATH, turned to follow it (spacing=0.4)
a.taper("Horn", along="Y", end=0.15) · a.twist("Horn", along="Y", angle=120)      # built straight, then shaped
a.bend("Horn", along="Y", toward="X", angle=70) · a.conform("Strap", "Body", toward="-Y", gap=0.005)
a.sweep("Horn", [(x, y, z), ...], 0.2, "bone", scale=[(0, 1), (1, 0)])    # a SECTION along a path, to a point
with a.scatter("Roof", pitch=0.25, facing=(0, -1, 0)): ...   # everything made inside: SPREAD over a surface
a.loop("Crate", "X", at=[0.35, 0.65]) · a.inset("Crate", "+Y", 0.12, depth=-0.05)   # box modelling, by rule
a.push("Crate", lambda c, n: n[2] > 0.9 and abs(c[0]) < 0.25 and c[2] > 0.45, 0.08) · a.round("Crate", 0.02)
a.smooth("Pod", levels=2, crisp=lambda c, d: c[1] < 0.01)    # the cut box SMOOTHED, all but its foot
a.repair("Bin")                                            # a part that is NOT closed: seams welded, flat holes capped
a.two_sided("Leaf")                                        # ONE sheet of faces: its back made, a hair behind it
a.cutout("Leaf", picture="refs/leaf.png")                  # its OUTLINE cut by the map (or keep=lambda p: ...)
a.anchor("Muzzle", pos)                                    # -> an Attachment on the spawned model
a.material("brass", **rbx.real("Brass"), wear=0.3)         # MEASURED albedo / metalness / roughness (lune run kit materials)
split = a.param("split", 0.5, lo=0.35, hi=0.85)            # a proportion `kit fit` matches to the references
rbx.Asset(..., style=["refs/x_style_1.jpg", ...])          # OTHER objects in the wanted style: look + outline report
```
**Build ONE, repeat it** (`a.repeat`, 2026-11-13): teeth, spokes, links, slats, studs, fins, stair treads -
never typed part by part, and never left out because typing them is long. Everything made inside the block is
repeated: a ROW (`step=` between copies), a RING (`around=` an axis through `centre=`: a full turn spaced evenly,
`angle=` for an arc with a copy at each end, `rise=` for a helix) or ALONG A PATH (`along=[points]`: from its
first point, where the part is modelled, to its last; `count=` end to end or `spacing=` studs apart; turned to
follow the path without rolling; `smooth=False` keeps the corners; a path whose last point is its first is a LOOP,
its copies evenly round it). `count` includes the part itself. `step`, `centre` and the path's points are read in
the `a.frame` open WHERE THE BLOCK IS OPENED: a frame opened inside the block turns the part, not the row. More than
a full turn of a ring needs `rise=` (a spring), and an option of another kind (a row with `angle=`) is refused.
Blocks NEST (a row in a row is a grid, a ring in a row two wheels) and combine with `a.mirror` (the mirror of the
whole row). `vary={"size": 0.1, "turn": 12, "shift": 0.02}` gives EVERY copy a small difference of its own about
its own centre, the same on every build and the same on a part's detailed and game versions: a row of teeth that
is not a stamp. The copies are the part's copies as a mirror's are: `a.cut`, `a.zone` (every copy zoned where the
part is: a tooth's painted tip on all twelve), `a.seat` and the gates take them with it; `a.stamp(at=)` is refused
inside, as in a mirror. NOT with it (card nrey): `a.fuse` joins the copies of what it absorbs into the ONE target,
`a.texel`'s density reaches the part and not its copies, `a.displace` reads its picture where each copy stands.
Copies that stayed identical share one piece of the texture on the parts route; a copy that differs (`vary=`), or
carries a stamp, a contact or a projected picture of its own, gets its own. The build says what it made:
`repeats: Tooth x12 (row x12), Peg x9 (row x3 in row x3)` and `facts.repeats` (the count is the block's copies; a
mirror doubles it; a repeated cutter is listed with `part: false`). Each copy is real geometry and counts in the
triangle budget: for hundreds of small things that only need to READ as relief, `a.stamp` or `a.scatter_relief`
stay the tools.
**Build it STRAIGHT, then deform it** (`a.taper`, `a.twist`, `a.bend`, `a.conform`, 2026-11-13; `rbx_deform`):
a horn, a hook, a fang, a scroll, a curved blade - never typed as a loft through hand-placed stations. A plain
tapered bar is easy to get right; then: `a.taper(part, along, end=0.15)` (its far end 15% of its section; or
`profile=[(share of the length, scale), ...]` for a belly or a waist; `keep="X"` holds one direction: a blade
narrows and keeps its thickness), `a.twist(part, along, angle)` (every section turned about the part's own length),
`a.bend(part, along, toward, angle)` (the length becomes an arc curling toward `toward`; the line through the
part's middle keeps its length; `start=` / `stop=` bend only a stretch of it, what lies past goes on straight).
`along` is the part's LENGTH in the model's frame ("X", "Y", "Z", "-Y" or a direction). Order matters: taper,
then twist, then bend (a bend first, and the others run along the old straight axis). The part is sliced first so
the deform has vertices: at the stretch's own ends (a taper from half way up starts THERE) and, for a curve,
every 10 degrees (`cuts=`). Refused, with nothing cut: a bend tighter than the part is thick, more than a full
turn (360 makes a ring), a COPY's name (name the part: its copies follow). A long tail past a bend of over 180
degrees can still run into the part's own stem: look at it.
`a.conform(part, onto, toward, gap)` LAYS a part built flat onto another's surface (a strap on a body, a plate
on a hull, a floater patch): every vertex moves along `toward` until the side facing it lies `gap` off `onto`
(measured along `toward`), the part keeps its thickness, a part already sunk in the surface comes back out onto
it, and what reaches past the surface's edge carries on level (the share of its vertices is said:
`deforms.past`). Bend, twist and taper move the part's copies as the part (`a.mirror`: a mirrored horn curls the
mirrored way; `a.repeat`: every tooth about its own middle; `a.scatter`: every piece as it was modelled);
`a.conform` lays each copy WHERE IT STANDS, onto what is under it. The detailed version (`a.cad` on the
high-and-low route) moves as one shape with its part, and a CAD part's own normals are turned with its surface
(slicing costs them about a degree). The build says it: `deformed: Horn (taper 0.15, twist 120, bend 70), Strap
(onto Body)` and `facts.deforms`.
**A section along a path** (`a.sweep`, 2026-11-13; `rbx_sweep`): a tapering horn, a tentacle, a cable, an
ornate handle, a rail, a moulding round a frame. `a.tube` is the plain case (one round section, one radius);
`a.sweep(name, points, section, mat)` carries ANY section: a radius (a regular polygon of `sides=`) or an outline
`[(x, y), ...]` drawn AS SEEN FROM THE PATH'S END LOOKING BACK at its start - x to the right, y to its up (`up=`:
the model's up by default, +Z for a path that starts straight up or down; carried along the path without
rolling, so a rail that leaves its plane does not turn along a straight leg). `scale=` is one number or
`[(share of the length, scale), ...]` (0 at an end is a POINT: a horn's tip; `(sx, sy)` scales the two ways
apart: a strap wider in its middle), `twist=` degrees turned about the path on the way, x toward y (a rope, a
drill; `[(share, degrees), ...]` for a turn that starts late; a twisted flat-sided bar is flat triangles between
its stations: a few percent inside the true twisted bar). `smooth=True` runs a curve through the points (a
station about every 10 degrees of its turning - a curve through three far-apart points bends tighter than the
circle they lie on: give more points); `smooth=False` keeps straight legs and MITRES their corners, so a picture
frame's four legs keep their section. `closed=True` (or a path that ends where it starts) is a loop with no
ends. Refused, with the place said: a part that would fold through itself (measured on the part as made: an
edge that would run BACK along the path - a bend too tight for the section, a leg too short for its mitres), a
corner of more than 160 degrees, a point in the middle of a path, a scale of 0 one way only. The build says it:
`swept: Horn, Rail` and `facts.sweeps` (each part's volume).
**Parts poured as one** (`a.cast`, S4 of his limitations review, 2026-11-17): spokes into a rim's barrel, a guard
into its grip, a bracket into its plate - joined with a TRUE fillet of `fillet_mm` radius where they meet (the
radius a pattern-maker leaves in every inside corner). `a.cast(name, [parts], mat, fillet_mm=)` - mode "auto"
takes the CAD route when every part is one a.cad part (their own code, each placed where its part stands, FUSED
in OpenCASCADE, only the edges lying on two of them filleted: an exact solid, its machined edges exact; on the
high-and-low route its low is the kit's own), else the distance-field route (`rbx_sculpt.rmin`, the round minimum
- smin's k is a width, not a radius; a voxel of the finer of 0.25 mm and a quarter of the fillet, coarser only
where the grid budget forces it, said; crisp edges snapped back onto their planes, `keep_sharp`; `grain_mm=` a
sand-cast skin, which turns the snapping off). Without `low=` the cast replaces its parts (a face budget of four
times theirs, 2,000..15,000); with it, the game mesh is the cast reduced to that budget and the full cast its bake
source. Held: `cast_fillet` (an error: a fillet that never formed - parts that do not meet), `cast_voxel` (a warn:
a voxel coarser than a quarter of the fillet). Measured (`test_cast.py`): a post on a plate with an 8 mm fillet -
the CAD route within 0.05 mm of a true 8 mm round at 1, 2 and 4 mm up and the plate's corner exact; the
distance-field route within 0.2 mm. Not held yet: on the high-and-low route the close-up fidelity of small
sharp-edged lows fails whether or not they are cast (card 3aan); the distance-field high's crease where the
fillet meets a crisp edge is stepped by its voxels (the CAD route has none).
**A moulding along a part's own outline** (`a.moulding`, H4 of his limitations review, 2026-11-17): a picture
frame, an architrave, a panel's raised rim, a cornice, a guard's edge bead. `a.moulding(name, profile, along,
mat, facing=)` - `along` a part's NAME with `facing=` (the outline of that part's faces turned that way: its
longest closed boundary, run counter-clockwise as seen from outside, the middle points of its straight runs
dropped) or a list of points (`closed=` for a loop). The profile `[(x, y), ...]` stands PROUD of the face (+y)
and runs INWARD over it (+x; x < 0 overhangs the edge). `mitre=True` (the default) cuts every corner on the
bisector of its two legs - the frame-maker's 45 degrees on a square; `mitre=False` runs a smooth curve. Every
swept part (a.sweep and a.moulding) carries its STRIP: per corner, the studs along its own length and the share
round its section (plain corner numbers, never a UV map: nothing exports them). Laid into a trim sheet
(`a.trim`), a swept part's side faces run the band BY THAT STRIP - round a curve and through every mitre with no
jump (only a loop's one closing point), V round the section across the band's height (`trim_fit` says a
section far longer or shorter round than its band is tall); its end caps are laid flat as before. A plan line
may name `a.moulding` (the methods lock holds it as a sweep). Proof: `test_moulding.py` (the strip on a square
loop and an arc; a 3 x 2 panel's frame mitred on all four bisectors, the band running 10 studs round it and 0.6 pi
round a half-circle rail with no jump).
**Spread ONE piece over a surface** (`a.scatter`, 2026-11-13; `rbx_strew`): scales, shingles, a field of
rivets, barnacles, studs, stones. Model the piece AT THE ORIGIN (of the `a.frame` the block is opened in),
standing on y = 0 with +Y its up, inside `with a.scatter(onto, count= / pitch=):` - each copy stands on `onto`'s
surface with its up along the surface's own direction there. The points are spread by AREA and keep their
distance (no clumps, no rows; the two sides of a thin part do not crowd each other), the same on every build;
`pitch=` is the least distance (as many as fit: give it the piece's own size and none lies on another),
`count=` so many (with both, fewer may fit: the summary says `9 of the 50 asked fit on Cube`).
`where=lambda centre, normal: ...` picks the faces (only the slope, only below the waterline) and `margin=`
keeps the pieces that far from the picked faces' border (none hangs over the roof's edge). Each piece is spun
about its up at random, or with `facing=(x, y, z)` every piece's +Z is laid along that direction on the surface:
shingles down a roof, scales down a tail. `sink=` pushes each a little INTO the surface (a flat foot on a curve
then touches all round); `vary=` as `a.repeat`'s, but about the piece's FOOT and shifting only along the
surface, so a bigger stone still stands on it. `onto`'s copies get pieces too - except inside an open
`a.mirror` / `a.repeat`, where the pieces are made on the part and the open block carries them to its copies.
The pieces are the part's copies, 512 at most, each real triangles (a field that only needs to READ as relief
stays with `a.stamp` / `a.scatter_relief`): `a.cut` takes them, and `a.zone`, `a.taper`, `a.twist`, `a.bend`
read the piece AS IT WAS MODELLED (its own y up, at the origin) - taper a scattered spike along "Y" and every
spike comes to a point, wherever it stands. Two scatter blocks on one surface do not know of each other. Said
as `repeats: Rivet x24 (scatter on Dome x24)` and `facts.scatters`.
**ONE box, cut into its form** (`a.loop`, `a.inset`, `a.push`, `a.round`, 2026-11-13; `rbx_poly`): the classic
way a hand-made prop is built - a crate, a case, a console, a chunky handle - instead of stacking separate boxes
(which reads as stacked boxes). Start SHARP (`bevel=0`), then: `a.loop(part, along, at=[shares] / count=)`
slices the part across its length so there is a face where the form needs one; `a.inset(part, where, amount,
depth=)` puts a flat rim inside the picked faces' border and moves the faces inside it straight in or out (a
lid's rim and sunk panel, a door panel, a bezel); `a.push(part, where, amount)` moves the picked faces along the
way they look and makes the walls behind them (over 0 a boss, a foot, a stub; under 0 a pocket);
`a.round(part, width)` rounds every sharp edge LAST, once (rounding first and cutting after leaves sharp cuts
through round edges; its width must be under half the part's shortest sharp-cornered edge - a pocket 0.03 deep
takes a round under 0.015). Faces are PICKED BY RULE, never by number: `"+Y"`, `"-X"` (the faces that look that
way within 12 degrees: a flat side, not the rounded strips beside it) or `lambda centre, normal: ...` in the
model's frame, as `a.zone`'s. A direction alone picks EVERY face that looks that way - the walls of a pocket made
a step earlier too - so say where the face is as well (`n[2] > 0.9 and c[2] > 0.45`); the build says
`push (2 places)` when a rule took more than one patch. A push's walls take the pushed faces' material. The
part's copies are modelled as the part is (a mirrored foot is inset on ITS outer side; a varied row each in its
own size). Refused, with nothing changed: a rule that picks nothing, a rim wider than the faces, faces that look
every way at once, a new wall that would lie ON a wall already there (a face at the part's own edge pushed IN:
inset first; a pocket's floor pushed OUT: make the pocket shallower), a result that is not a closed solid or
has two faces lying on each other, a copy's name, a CAD part (its shape is its code's; `a.loop` may still cut
it). The build says it: `modelled: Crate (inset +Y, loop x2, push, inset, round 0.02)` and `facts.modelled`.
**EVEN THE FLOW** (`a.flow(part)`, 2026-11-17; `rbx_flow` - LoopTools Relax / Space): loops bunched together
(`a.loop` packed at one end, a generated mesh's crowded rings) spread out evenly and needle triangles open up,
the shape held exactly: every vertex slides over the part's own surface toward its neighbours' middle; one on a
sharp edge (over `sharp=` 30 degrees) or the border slides only where that edge runs STRAIGHT; a corner, or a
curved rim, never moves. Copies move the same way; the detailed version on the high-and-low route is left alone.
`facts.modelled` says how even it was and is (`spread_before` / `spread_after`: 0 = evenly spaced) and how far any
vertex lies off its surface (`off_mm`). A vertex keeps to its own smooth region (never across a sharp edge onto a
cap); a line between two materials is held like a sharp edge. Refused, nothing moved: a part of nothing but
corners (a plain box), a CAD part (its tessellation is its code's), a mesh still carrying its own painted map
(`gen_uv`), a copy changed where it stands (`a.conform` first: flow before it). Faces under
`sharp` count as one smooth surface: a 16-sided rod's sides re-facet slightly (within its chord), say `sharp=20`
to hold its facets as they are.
**... then SMOOTH it** (`a.smooth`, 2026-11-13; `rbx_subd`): the other half of box modelling. A SHARP box
(`bevel=0`) cut into a rough form (`a.loop`, `a.inset`, `a.push`) and then subdivided (Catmull-Clark, `levels=`
1..4, each four times the faces; 1 leaves facets, 2 reads smooth) becomes a pod, a helmet, a moulded handle, a
pebble, a seat - forms `a.cage` could only make from a traced outline extruded flat. `crisp=` says which edges
are HELD: `None` (none: a sharp box becomes a pebble), `"sharp"` (every edge sharper than `angle=`: a part of
flat faces keeps its shape exactly; rounded strips under the angle - a default bevel, a cylinder's side - go
soft), or a rule `lambda centre, way: True / False / 0..1` on each edge's middle and direction (the model's
frame; the direction's largest part is made positive, so `d[2] > 0.9` is every edge along z) - `c[1] < 0.01`
holds only the foot. `hold=` is how hard a held edge stays, the same at every level count: 1 a true edge, 0.75
slightly eased, 0.5 clearly rounded, 0.25 soft but still an edge. A held outline keeps its corners
(`corners=True`: a held foot stays the full square), and with `"sharp"` a flat face keeps its plan: the edges
that only divide it between two held edges (a rim's mitres round a sunk panel) are held with them. Faces of more
than four corners or with a dent (what `a.cut` leaves round a hole) are split first, so a cut part smooths too.
A soft part is SMALLER than its cage (a sharp box all soft: about a third of its volume, 85 to 88% of its
width): build the cage bigger, or hold what must keep its size; a cut close beside an edge (`a.loop`) holds it
the way a modeller's holding loop does. Copies are smoothed as the part; face materials are kept. Smooth
INSTEAD of `a.round` (a smoothed part has no sharp edge left for it). Refused, with nothing changed: a result
with one face through or on another (hold more edges, cut the faces smaller, or other levels), a CAD part, a
copy's name, a rule that answers outside 0..1, more than 120,000 faces. Said with the other steps:
`modelled: Pod (loop x2, push, smooth x2)`.
**A part that is NOT CLOSED** (`a.repair`, the `openings` and `patched` checks, 2026-11-13; `rbx_repair`): the
`manifold` gate only counts open edges; the build now says WHICH part is open and WHAT the opening is, because
each kind has its own answer. A SEAM never welded (two edges on each other, their points a rounding error apart)
is welded by the build itself, like a boolean's tear (never into an edge three faces share, and not on an asset
that said `require_manifold=False`). A flat HOLE (a missing cap: a tube's end, a face a cut took
with it) is capped by `a.repair(part)` (a ring-shaped one - a thick pipe's end - as ONE face with its hole) - call it right after an `a.mesh` / `a.import_mesh` that is not closed, and
before `a.inset` / `a.push` / `a.smooth`, which refuse a part that is not a solid. NO repair is right for an open
rim that is not flat (build its missing faces), for a slit (give both its sides the same points) or for the border
of a surface with no thickness (model it as a solid): `a.repair` refuses them with the part as it was, and a
build with one left fails `openings` by the part's name. The build's own last pass still fills every hole it can
before the join; it now SAYS so (`repaired: Lid (1 opening filled by the build)`) and warns `patched` when the rim it
filled was not flat - that patch closes the part and is not its true surface: look at it.

**A surface with NO thickness** (`a.two_sided`, 2026-11-14): a leaf, a banner, a cloth's hem, a hair card are
ONE sheet of faces - and a sheet is no solid (it fails `openings`: "the border of a surface with no thickness").
`a.two_sided(part)` makes its back as real faces: the same faces turned over, a hair behind the front
(`thickness=0.01` studs), joined to it by a rim along the border. The part is then a thin closed solid: it passes
every closed-solid gate as it is, each side is seen and lit from its own side in ANY engine (no two-sided switch
on the mesh is needed - whether a game script may set Roblox's own was not checked in Studio), and the two sides
get their own places on the map, so a leaf's underside can be another colour. It costs the sheet's triangles
again plus its rim. (The back laid exactly ON the front was tried first: closed too, and the bake's shading rays
could not tell the two sides apart - a banner came out in blotches.) Shape the sheet first (`a.bend` /
`a.taper`), then give it its back; its copies get theirs.

**An outline cut by the map** (`a.cutout`, 2026-11-14; `rbx_cutout`): a leaf's edge, a grille's bars, chain-link,
torn paper are far too fine to model - they are HOLES IN THE COLOUR MAP'S ALPHA, and Roblox cuts them out of the
mesh (SurfaceAppearance.AlphaMode = Transparency with the part's own Transparency 0: a hard cut, sorted by depth).
`a.cutout(part, picture="refs/leaf.png")` lays a picture flat and upright on the part's own plane, the right way
round from where the model is looked at (its front, its side, from above: lettering is never mirrored there) -
solid where it has alpha, or where it is dark; `a.cutout(part, keep=lambda p: ...)` asks a rule the point of the surface under
every texel, in the model's frame (a copy is asked where the part stands). The geometry is not touched: the part
stays a plain sheet (give it its back with `a.two_sided` first); after every bake the group's colour map is written
again WITH the alpha beside the bake's own (`..._color_cut.png`: the bake's file, its cache and its kept passes are
untouched), the cut carried into the margin round the islands so no line shows when the map is filtered; the
manifest marks the group and the model file sets the mode. Keep cut parts in a group of their own (`group="cut"`):
the mode is the whole group's, and the build warns (`cut_group`) when solid parts share it. Identical parts are
not laid on one place of the map when one of them is cut. The build says how much of each map is cut (`cut out:
Grille 50%`); a cut that takes nothing or everything fails (`cutout`). A game version (`kit optimize`) runs the same
script, so it is cut the same way. NOT covered: soft edges (the cut is hard: 0 or 255), and how it looks in Roblox
itself - the mode is set from Roblox's own documentation and was not looked at in Studio.

**THE REFERENCES, SOLVED TOGETHER** (`a.cite`, 2026-11-16; `rbx_agree`; his D-R01). What a model's references
say about its overall sizes comes from different places, and each used to be checked alone against the build -
so a trace of a 4:1 object beside sourced sizes of a 3:1 object made a build nothing could satisfy, and nothing
said which was wrong. Now every such statement is ONE CLAIM with a tolerance: the pack's sourced sizes
(`object.length / height / width`, by their trust: high 2%, medium 5%, low 10% - read whether or not the
script calls `a.pack()`), each traced side or front view's own proportion (`a.trace_match`: 4%; a trace with
bar=0 or `a.not_reference` says nothing), and what the script cites -
`a.cite("maker's drawing", 1000, axis="length", trust="high")`, `a.cite("side photo", 0.25, of=("height",
"length"))`. The script's own `Asset(size=)` is NOT one: it is the aim. The build fits the three sizes to all
of them at once, weighted by trust, then HOLDS EACH OUT and predicts it from the rest, scored against what the
claim and the prediction can be trusted to together. Held: `reference_agree` (an error) names a statement more
than two and a half of that from what the others say, with both numbers, takes it out and looks again - with a
majority against it only the odd one is named; where no majority exists (two alone, a ring of three) all are,
the least trusted first. `reference_fit` (a warning) says where the BUILT model is over 5% off what they agree
on (its sizes where they fix any, else its proportions). The summary: `references: 4 statements agree`. Axes:
height is Y, length the model's Z (what a side view sees across; a weapon's barrel), width its X (what the
front view sees across). NOT in the solve (still each on its own check):
sections (`a.section_match`), a measured form (`a.form_match`), a top view's proportion, part-level sizes
(`slide.length`), a trace's `dont_care` regions; no camera is solved here (`kit camfit` fits one picture's).

**An opening that must STAY open** (`a.open_way`, 2026-11-15; `rbx_through`): a bore, a sight line, a slot a strap
runs through. A game version's retopology rebuilds the surface and can lose a fine bore (measured: a 0.12-stud bore
gone at a 400-triangle budget), and a part can simply be modelled into the way - nothing knows which opening the
design needs. So NAME it: `a.open_way("Bore", (0, 0.5, -2.2), (0, 0.5, 2.2), 0.3)` - a straight way from one point
to another (start and end a little OUTSIDE the model), so many studs across; inside `a.frame` it is read in that
frame. The build looks down it with fifteen lines of sight (the middle, a ring at 0.8 of the half width, a ring at
0.4), on the parts as modelled (a `--geo` round too) and again on the meshes it exports. A line that is stopped
FAILS the build (`open_ways`) - a game version too - by the opening's name, what stands in it and where; the
summary says `openings: 2 open`. What it does NOT do: find an opening nobody named; prove more than its lines (a
wire thinner than the gap between two of them passes); follow a way that is not straight (one call a leg); a
sight line laid ON a face is stopped by that face; faces `a.cutout` cuts away still count.
A REPAIR IS STEERED BY THE NAME (his D-R12): a hole the way passes through - its middle line crossing the hole's
own plane inside the hole's outline - is NEVER capped, by `a.repair` or by the build's own tear closing;
everything else is closed as before, and the facts say `left open as named: <opening>`. Holes in one plane are
one opening with islands: a thick tube's missing END (an outer loop round the bore's own) is still capped - the
way runs through the bore, not through the missing ring. Say `a.open_way` BEFORE `a.repair` (after it, the
build stops and says so). A
named opening in a sheet (a wall with no thickness) leaves the part open: `openings` fails and says so -
`a.two_sided` gives the wall its back and keeps the opening. NOT steered: the game version's reduction and a
generated skin's remesh (`kit sharpen`) - there a closed way is still only CAUGHT (`open_ways` on the export).

**The map across its seams** (`seams`, 2026-11-15; `rbx_seams`): every edge the unwrap cut lies in two places of the
map. After every bake the colour map is read ACROSS each cut edge that runs over smooth surface (its two faces turn
30 degrees or less, or the mesh shades the edge smooth; a seam on a sharp edge is hidden by the crease and not
judged): two points inside each island, in windows of 16 texels along the edge, with the colour's own run through
the seam taken out - what is left is the seam's own step, seen from 12/255. The same reading is taken with NO seam
in it (inside one island): the map's floor. The build says it (`seams: ball meet (100% of their length judged)`)
and WARNS when the seams show a step on 5% more of their length than the floor, naming the worst places in studs.
The usual causes: a texture laid by its place in the map and not in space, a picture projected from one side, a
seam cut across an open face (move it to an edge, or under another part). Measured read-only on 16 texture groups
of built models: a plain baked ball 0%; the car rim's three groups 0%, 0% and 3% beyond their floor; a figure
textured by projected pictures 3% to 22% (its arms the worst). The first version of this check compared one side
with the other and read the TEXTURE, not the seam (its one review's null test showed the same shares with no seam
at all): never judge a seam without its floor. It warns, it does not fail; only the colour map is read; whether a
measured step is seen on a model was not looked at one by one; edges under 3 texels long and edges three faces
share are not judged (the summary says how much of the seams' length was).

**The map itself, checked** (`uv_overlap`, `uv_stretch`, 2026-11-13; `rbx_uvcheck`): after every bake each group's
map is read for what its texel density cannot show. `uv_overlap`: faces lying on each other on the map by
accident - one of them shows the other's paint - as the share of the map painted twice, the faces, the part and
the place (u, v) to look at. Only a copy the unwrap ITSELF laid on its original's place (its own record, on the
route that unwraps by part) is meant and left out: two faces on the very same place with no such record - a front
unwrapped onto its back - count like any other two. The number is the patch's inside (three texels of the
checking grid wide or more): a hair of overlap along a seam is not counted. `uv_stretch`: texels lying longer than wide over the surface (over 2 to 1), which makes the map
that many times coarser one way than its density says. Both are ERRORS since 2026-11-17 (they were warnings; the
owner's limitations review asked for them to block): of 141 built groups read as they are, 102 have no texel
painted twice and 15 are over the bar of 0.1% (a knife's screws and ribs and a game version's collapsed arm at 1%)
- those fail when rebuilt, with the part and the place to fix.

**Code CAD for hard-surface parts** (`a.cad`, build123d on OpenCASCADE — `lune run kit tools setup cad` once): a
receiver, a barrel, a rail, a ring, a grip — anything machined — as an EXACT solid: fillets, chamfers, holes, shells,
sweeps, lofts, threads come out clean at the size the code says (no boolean slivers, no guessed bevels). The code is
millimetres in the kit's axes (x right, y up, z back: the front is -Z), build123d's names already imported, the part
left in `part`; measured numbers go in as `params` (`P` in the code). 1 stud = `a.real_scale()` mm (else 280).
**Real fasteners and springs (down to the screws):** every a.cad part script has kit/tools/cad_parts.py's helpers —
`screw("M3-0.5", 10, head="socket"|"button"|"countersunk"|"pan"|"hex", threads=False)` (ISO tables; its head's
top at z 0, its shank down -Z), `nut("M3-0.5")`, `pin(d, length)`, `roll_pin(d, length)`, `spring(mean_d, wire_d,
length, coils)` (a wire swept along a helix, ground ends), `clearance("M3")` (the ISO 273 hole: cut it in the host:
`part = Box(...) - Rot(90, 0, 0) * Cylinder(clearance("M4") / 2, 40)`). Sizes from `kit refs dims find "iso 4762
m3"`. Gate `fastener_seat` (an error at hero / aaa): a screw / pin / nut / spring / a.internal() part with more than a
third of its volume inside another part's SOLID has no hole or cavity — cut it; `fastener_support` catches the
opposite (a pin spanning air). Beyond these: `from bd_warehouse.fastener import ...` (washers, set screws,
`bd_warehouse.thread`, bearings, gears).
**Shapes that WRAP around (gate `section_match`):** a grip, a stock, a shroud is not an extruded box. `kit refs measure
<model>` records the reference's horizontal slices (`levels`: at each fraction of the height the biggest island's
width, depth and squareness — 2 = an ellipse, 6+ = a box; a real 1911 grip reads ~2). Build FROM them in an a.cad
part: `part = loft_sections(from_levels(P["levels"], height_mm, length_mm, hs=(0.1, 0.2, 0.3, 0.4)))` with
`params={"levels": <the measure.json levels>}` (also `section(w, d, squareness)`, `loft_sections([...], axis="z")`
along the length). Check it: `a.section_match("<ref>", levels=(0.15, 0.3, 0.45))` slices the build the same way and
names a slice boxier than the reference's (by > 1 squareness) or of other proportions (> 25%). Measure the reference
facing right (`--front min` when its muzzle points left), or the grip lands at the front.
**Curves, not polygons (gate `faceting`, an error at hero / aaa):** a curve is judged by how far its facets sit from
the true curve (the sagitta) — hero 0.08 mm, prop 0.25 mm: 16 sides are fine on a 3 mm pin (0.03 mm), not on a 40 mm
barrel (0.38 mm). Give a.cylinder / a.tube enough `segments`, or build it in a.cad (tessellated to 0.05 mm). Real
models: typically 0.067 mm (`kit learned show firearm`, facet_sag_mm). UVs: the kit unwraps every group itself
(smart projection, 66 deg): its seams fall on corners and nothing stretches past ~1.2x — check a build's per part
with `kit library inspect build/models/<asset>.blend ...` (uv_layout: seams_across_flats, stretched_share, px/mm)
and `kit learned compare`.
**Bevel everything (gate `sharp_edges`, an error at hero / aaa):** every visible part's hard edges (> 30 deg) are
measured like a reference model's (kit/refs/dissect.py): the share that is bevelled must reach half at hero (a quarter
on a prop) — and with `a.learned_from("firearm")` what REAL models of that kind do for that part's role (a frame:
~96%), the fix naming their typical bevel size (`kit learned show firearm`: bevel_size_mm by role). Round edges in
CAD (`round_edges`, `fillet_soft(edges, r)`; `fillet_each(hard_edges(), r)` rounds exactly what is STILL sharp —
two faces meeting at > 30 deg, one edge at a time — and leaves a fillet's own tangent seams alone: a screw's slot
lips, a turned part's corners, a magazine's outside; a fused feature a fillet breaks (OpenCASCADE refuses it, the solid
goes invalid) gets its corners chamfered in its own sketch instead), in boxes / extrusions (`bevel=r`). When OpenCASCADE REFUSES a fillet
outright, a.cad bevels the part's still-sharp edges on the mesh instead (at most 12% of its thinnest side, 4
segments) and says so (`cad[].bevel_fallback_mm`) — never a sharp edge left in silence.
**The fast loop: `lune run kit cad check <asset>`** runs every a.cad part of the build script in SECONDS, without
Blender (closed solid? volume, faces, open edges, fillets it had to shrink, or the error / crash line). A build is
minutes: never debug a part's CAD inside builds — check, fix, check, and build only when every part is ok.
`--look` also DRAWS each part (four sides, Blender, seconds: build/cad/<asset>_<Part>.png; `--zoom cx,cy,cz,size`
in the part's mm) — see a fin, a step or a fillet that did not take before any build. Openings in a plate (a trigger
guard's): union their shapes in the 2D PROFILE before extruding and round the edges in the same pass — 3D cuts of
different widths, and box cuts thinning a rounded part, leave knife-edge fins at curved corners.
```python
a.real_scale(280)
a.cad("Receiver", """
    with BuildPart() as part:
        Box(100, 60, 240)
        fillet(part.edges().filter_by(Axis.Z), 6)          # the four long edges
        with Locations((0, 0, 120)):                        # the back face: a Hole cuts down from it, right through
            Hole(10)
    """, "frame", pos=(0, 1.2, 0))
a.cad("Barrel", "gjallarhorn_barrel.py", "gunmetal", params={"r": 18, "L": 700})   # assets/models/cad/<file>
```
Pick edges by what they ARE, not only where they are: the ends of filleted edges are quarter-circle arcs too, so
"the circles at the front" also takes them — filter by radius (`abs(e.radius - 10) < 1e-6`). Organic shapes (heads,
feathers, cloth) are not CAD's: sculpt them (a.sculpt; relief, displace, kit gen). Gate `cad_solid`: the part must be a valid,
closed solid (a sketch never extruded is named). `tol` (mm, 0.05) and `angle` (degrees, 12; 6 for a big curve that
fills a close-up) set the facets; an unchanged part is read back from build/cad, not rebuilt.
**Real 3D forms, not boxes** (the difference between "programmer art" and a designed object):
```python
a.carve("Slide", "slide", side=outline, top=outline, front=outline)   # 2-3 orthographic outlines intersected:
                                                     # tapered in plan, chamfered in section, shaped in profile
a.loft("Grip", stations, "grip", axis="Y", squareness=3.4)            # rounded-rectangle sections (grips, handles)
a.fuse("Frame", "Grip", "TriggerGuard")              # ONE solid, filleted seams: moulded/cast, not kitbashed
a.cut(target, cutter)                                # the cut's new rims + floor corners are bevelled automatically
with a.internal(): ...                               # enclosed mechanism parts (springs, striker, rounds): allowed
                                                     # inside, shown in the schematic's section
a.joint("Slide", "slide", "slide", axis=(0, 0, 1), max=0.38)          # moving part = own mesh + Motor6D in game
a.joint("Trigger", "trigger", "hinge", axis=(1, 0, 0), pivot=p, max=14)  # Models.pose(model, "Trigger", 10)
a.joint("SlideMarks", "slidemarks", "fixed", axis=(0, 0, 1), parent="slide")  # markings riding on a moving part
a.joint("Shell", "shell", "slide", axis=(0, 1, 0), max=0.4, after={"Housing": "max"})  # a SEQUENCE: lifts out only
                                                     # once the housing has slid open — checked with it open
a.real_scale(162.5)                                  # mm per stud -> the schematic dimensions in mm
# rbx.Asset(..., kind="chair"): what it is in the real world (kit/real_sizes.json: chair, door, desk, bookshelf,
# double_bed, wall, ... — ranges read from Infinigen, each row linked to its source) -> size_plausible WARNS
# when the measured size is outside the range by over 25% (studs -> metres via real_scale, else 1 stud = 0.28 m)
```
**Hard-surface kit** — `import rbx_parts as P` (outline + plane + surface + side like extrude):
`P.plate` (raised chamfered armour) · `P.inset_panel` (recessed chamfered panel) · `P.groove` (angular panel line,
45° corners) · `P.stripes` (hazard bands) · `P.screw(s)` (socket head) · `P.latch` · `P.knurl` · `P.connector` ·
`P.fins` · `P.led` · `P.vent` · `P.bolts` · `P.rivets` · `P.grip` · `P.frame` · `P.light` · `P.wheel` · `P.handle`.
Hierarchy: primary forms (the silhouette) → secondary (plates, insets, grooves, clamps) → tertiary (screws, text,
LEDs, stripes) placed ON the secondary forms. Every hard-surface face people see needs a secondary form. Wood is
not hard-surface: its detail is the boards themselves, the grain, and the hardware (nails, bolts, hinges, handles on
mounts, stencils) — never grooves carved into a plank to fill it (the score sees grain: texture and empty measure
the albedo a player sees, and 4+ grooves carved into wood cost the whole score through craft).

Warnings that name a habit, never charge it: `tiny_cuts` (a blind cut smaller than a finger: model it ON the surface
inside `with a.floaters():` — baked, zero triangles; a master keeps its recesses), `cut_through` (a cut that splits a
part), `declared` (an opt-out the script switched on).

### Templates (start here when the category has one)
**Firearms** — `import rbx_firearm as F` (kinds: sniper, assault, smg, shotgun, **railgun** · styles: military,
scifi, **dark**):
```python
gun = F.Firearm(a, "railgun", length=5.2, style="dark")     # boxy armoured sci-fi rifle with a full AAA detail pass
gun.set(optic="compact")                                    # stock/muzzle/handguard/optic/mag variants: F.VARIANTS
gun.build()                                                 # parts + anchors: Muzzle, Grip, Support, Bolt, Sight
```
Origin = the grip → `Models.tool(...)` needs no Grip offset. No template? Look up the real object's dimensions,
write the ratios in the docstring, build from them, `a.expect(...)` the ones that matter.

**THE TOPOLOGY, MEASURED** (2026-11-15; `rbx_topology`). Every build reads its game mesh for four things a modeller
looks for, and says each as a warning with the part it is on:
- `polygon_waste` - triangles spent on nothing: vertices in the middle of a flat face (every triangle round them
  in one plane, not on a seam of the map or a part's border). Over 20% of a group: build that face coarser.
- `needles` - triangles over 500 times longer than wide AND under 0.005 studs across (a bevel's long strip is not
  one). Over 0.5%: weld the points that nearly meet.
- `poles` - a point where more than 16 edges meet on a curved surface (a cone's tip): the shading pinches. The
  middle of a flat cap is not one.
- `hidden_faces` - faces no eye outside can reach: from seven points of each triangle (its middle, each corner,
  each edge), 24 directions out all end on the model. Parts sunk into each other - the kit's way of building -
  hide 10 to 25% of a healthy model: that is in the facts (`topology.<group>.never_seen`). Over 30% it warns:
  `a.drop_hidden()`.

`a.drop_hidden(group=None)` takes those faces out before the unwrap, so neither a triangle nor a texel is spent
on them: `hidden faces dropped: main 15`. A polygon goes only when 64 directions are blocked from its middle, a
hundredth in from every corner and every edge, and from a grid over it a step every fiftieth of the model: a
face with a strip in view stays whole. Only what is SOLID and CANNOT MOVE covers a face: a group with a joint
hides nothing of another group, and a cut-out part (a grille, a leaf card) or a material with alpha under 1
(glass) hides nothing at all. The rim a dropped face leaves is an open edge you meant: the closed-mesh gate
knows it. NOT asked: an eye lower than about 10 degrees to the face, and a gap narrower than the rays find -
look at the sheet once. On a big group it costs seconds (448 rays a covered triangle).

`a.shade(part, "flat" | "smooth" | degrees)` says a part's shading where the 35-degree rule is wrong: a faceted
gem flat, a shell smooth whatever its angles, a body hard only past 60. Held: the exported mesh's own corner
normals are read and `shading` FAILS when a part asked flat is shaded round, or one asked smooth is flat (a
number is applied and said, not held). Not on
the high-and-low route (its shading is the baked normal map's: shape the high).
NOT built: a tool that takes the wasted vertices out for you (`polygon_waste` only says them); edge flow for a
mesh that bends (a character's loops round a joint) - the kit's game meshes are rigid parts.

**A SURFACE DRAWN BY CONTROL POINTS** (`a.patch`, 2026-11-15; `rbx_nurbs`; a NURBS patch). For a shape that is
neither turned, extruded nor lofted - a wing, a saddle, a fender's flare, a leaf's cup. Give a NET: rows of
points the surface is pulled toward (it passes through the net's four corners, runs smooth between, and stays
inside the net's hull):
```python
net = [[(-2, 0, -1), (0, 0.6, -1), (2, 0, -1)],
       [(-2, 0.3, 0), (0, 1.2, 0), (2, 0.3, 0)],
       [(-2, 0, 1), (0, 0.6, 1), (2, 0, 1)]]
a.patch("Wing", net, "paint", steps=(16, 16), thick_mm=15)
```
It is a closed solid with a wall of `thick_mm` (the wall grows on the side the rows-then-columns turn away from;
reverse the rows for the other side). `degree=1` is straight between the points. Held: the build STOPS on a net
that folds the surface over itself, on a wall thicker than the surface's tightest bend (the back would run
through itself), and on a net whose points lie on one line. JOINED (2026-11-17): a net whose first and last
column (or row) are the same points is a RING - its seam welded, no wall there; a row gathered into one point is a
POLE - one point per skin, its wall as thick as the rest (a cone's tip, a dome's top); the build says which
(`design.surfaces[].joins`). A net closed both ways (a torus) STOPS: sweep a ring for that. NOT built: weights on the points (every point pulls alike - no exact circle
from a net; turn a circle with `a.lathe`), trimming curves, joining two patches smoothly (lay their shared row
and the row next to it in one line yourself).

**SHAPES THAT FLOW TOGETHER** (`a.blob`, 2026-11-15; metaballs). Balls that melt into one skin where they come
near - a cartoon puff, a lump of wax, a boulder's mass before it is cut:
`a.blob("Puff", [(0, 0, 0, 1.0), (0.9, 0.3, 0, 0.7)], "smoke", resolution=0.08)` - balls are (x, y, z, radius)
in studs, `resolution` the skin's cell (smaller = smoother; the triangles grow fast: read the build's count).
One closed mesh. Held: the build STOPS on a ball too small for the resolution to show, on a skin that did
not close, and on a metaball already in the scene under its name (Blender melts metaballs of one base name into one
skin; a part's name loses its dots for that reason). The skin is Blender's: a ball alone comes out at its radius (within 3%); where two meet they swell
into each other, so read the built size off the preview.

**A PART LENT BY ANOTHER BUILD** (`a.kitbash`, 2026-11-15; kitbashing).
`a.kitbash("Pommel", "claymore", "Pommel", "steel", pos=(0, -0.4, 0), scale=0.8)` takes the SHAPE of one named
part out of another model's saved build (`build/models/<asset>.blend`), centres it at `pos`, and gives it THIS
model's material - a build lends its shape, never its look (the originality rule). Held (the owner's rule,
2026-10-08): ONLY A BUILD HE APPROVED LENDS ITS GEOMETRY - its last verdict a 7 or more, or keep; any other
STOPS the build and says what its verdict is (a guessed row counts for nothing). Build the lender first. A lent
part comes as its build LEFT it: its bevels and its triangles at the lender's fineness (scale it far up and it
shows), and without any face that build dropped as never seen - this build closes such an opening and says so
(`repaired`). Held (2026-11-17): his verdict is on a BUILD, not a name - a lender whose saved build was written
after his last verdict STOPS (it says when, and the build_id he judged when the verdict names one: `kit verdict
... --build <its build_id>` records it, and that build lends again). The car rim's S2 rebuild lends nothing until
he scores S2.

**HAIR AND FUR: LOCKS ALONG A FLOW** (`a.lock`, 2026-11-15). THE ENGINE has no hair system and the kit ships
rigid meshes: hair, fur, grass and feathers are STRANDS OF GEOMETRY, placed by the scatter tool - which is the
groom: where they root (`where=`, `margin=`), how dense (`count=` / `pitch=`), which way they lie (`facing=`: a
nap), how they differ (`vary=`).
```python
with a.scatter("Scalp", count=140, facing=(0, -0.2, -1), vary={"size": 0.35, "turn": 12}):
    a.lock("Lock", 1.1, 0.14, "hair", droop=0.6)              # long hair, swept back
with a.scatter("Pelt", pitch=0.06, facing=(0, 0, -1), vary={"size": 0.4}):
    a.lock("Tuft", 0.12, 0.05, "fur", droop=0.3, segments=2)   # fur: short, dense
```
`a.lock(name, length, width, mat, droop=, curl=, segments=)` is one tapered strand standing at the origin and
bending over toward +Z (`droop` 0 = straight up, 1 = it ends level, 2 = it hangs): a closed solid of three
sides, so it needs no alpha and no back. A lock is 6 x segments - 2 triangles: 22 at 4 segments, 3,080 for a
head of 140 - count them. Hair does not move: a part that sways is the animation lane's (an accessory's own
joint).

**A HAIR CARD BENT ALONG A FLOW** (`a.card`, 2026-11-17; `rbx_card`). A narrow strip laid along the hair's flow
from root to tip, carrying a picture of many strands in its alpha - one card reads as a lock of a hundred hairs:
```python
a.card("Fringe", [(0, 2.0, -0.4), (0.1, 1.9, -0.7), (0.15, 1.5, -0.8)], 0.35, "hair",
       picture="refs/strands.png", taper=0.4, twist=20, cup=0.1)
```
`along` is the flow, root first (a smooth line runs through the points); `width` across at the root, `taper` the
tip's share of it (0 = a point), `facing` the way its face looks at the root (default the front), `twist` degrees
it turns about the flow root to tip, `cup` its middle bowed toward its face. The STRAND PICTURE is read in the
card's own coordinates - its top at the root, its bottom at the tip - so it bends with the card (`a.cutout` lays a
picture flat in one plane: on a lock that turns back up, the flat picture cut 0.625 of it where the card's own
cut its tip half, 0.393). The card is made two-sided. Read its strands' width in texels: a strand a texel or two
wide comes out grainy (the probe at 512 px) - give the hair's group its map size (`a.texel`). A flow that doubles
back sharper than 150 degrees between two rows is refused (two cards). Held: `cutout` (a cut taking nothing or
everything fails). Proof: kit/test/python/test_card.py.

**A CLOTH LAID BY SIMULATION, THEN FROZEN** (`a.cloth`, 2026-11-15; `rbx_garment`). A flat sheet dropped over
parts in Blender's cloth simulation and kept as the still it comes to rest in: a tablecloth, a tarp, a flag hung
by an edge. The game gets a plain mesh; nothing is simulated there.
```python
a.cloth("Cover", (3.2, 3.2), (0, 1.3, 0), "linen", over=["Table"])           # falls on it, hangs round it
a.cloth("Flag", (2, 1.2), (0, 3, 0), "silk", pin=lambda x, y, z: z < -0.55)  # hung by one edge
```
Put it ABOVE what it falls on. `cells` (squares a side: finer folds, slower, more triangles - 20 cells with its
wall are about 6,700), `frames` (how long it falls), `bending` (0.1 silk to 5 leather), `thick_mm` (its wall).
Held: `cloth` FAILS when the sheet never came to rest on what it was laid over (pinned or not), fell past
it, or lies inside it. A cloth at rest lies a hair off what it rests on (the simulation's own gap): the two
count as touching. Garments on an
R6 body keep their own route (`rbx_garment` tubes on the body's blocks).

**A SEWN SEAM** (`a.stamp("stitches", ...)`). A row of thread dashes in the normal map, no triangles: each a
round thread that dives into the cloth at both ends. `pitch_mm` (a stitch and its gap: twice the thread at
least), `thread_mm` (never wider than the stamp); it runs
along the stamp's long side. A seam line between two panels is `a.stamp("panel_line", ...)`.

**A DRAWN ORNAMENT** (`a.ornament(...)`, H4 of his limitations review, 2026-11-17). Scrollwork, filigree, a crest,
an engraved border: drawn once as a picture - an `.svg` (its FILLED shapes; Blender's own importer draws them at
2048 px, holes kept open; a drawing of lines only is refused), a `.png` (dark lines on light paper, or by its
alpha; `invert=True` for light on dark) or an `.npy` - and stamped into the normal map like `a.stamp`: centre `at`,
`width=` or `height=` in studs (the other from the picture's proportions), `facing`. Raised `depth_mm` or engraved
(`cut=True`: darkened in the colour like a stamp's recess); its edge shaped over `edge_mm` (default: the depth) by
`profile`: "round" (a rounded bead), "v" (an engraver's V: a chamfer to a ridge), "flat" (a sharp wall) - from
the EXACT distance of each pixel to the drawing's border (`rbx_stamps.inside_distance`), never a blur. The thinnest
stroke (`rbx_stamps.stroke_widths`: a 5th percentile over the strokes' middle lines) is what the `stamp_texels`
check holds to 2.5 texels of the baked map. A plan may name it (`a.ornament` in a parts plan line: the methods lock
holds the build to it). What it is NOT: geometry - an ornament that must stand out in silhouette is modelled
(`a.relief` from a picture, `rbx_parts`). Flat, it projects along `facing` like every stamp (it fades out where the
surface turns past about 70 degrees); on a round part give it `around=("Y", centre)` (any stamp takes it too): it
WRAPS round that axis, its width laid as arc length from `at`, its height along the axis - a grip's band, a
barrel's engraving, a column's scroll. Proof: `test_ornament.py` (a steel plate with an .svg crest and an engraved
.png scroll: upright, not mirrored, the crest's hole flat, the engraving darker; a scroll shrunk to 2 cm said too
fine; the scroll wrapped round a 0.3-radius drum reads out to its drawn +-67 degrees, projected flat it is gone by
60).

**DEFORMING CHARACTERS AND GARMENTS** (his D-R06). The kit's bodies are R6: six rigid blocks, each a part moved
by a joint - the owner's rule. Nothing bends, so there are no skin weights to check and no joint to deform
across; a garment is rigid pieces fitted to the blocks and proven clear of each other in every pose
(`rbx_garment.clip_check`). A skinned, bending character (R15 / a mesh deformed by bones) is NOT built: it is
another route - bone weights, a deformation test at every joint, topology made for bending - and it is out of
the R6 rule, not forgotten.
