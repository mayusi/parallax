<!-- reference for the parallax-3d route card; verbatim from the skill page (2026-10-16) -->

## Stage 6 — Surface: every part's finish from data
Every part gets the surface its references show — not a default grey: its finish (`rbx.finish`, `rbx.real`, a scan),
its pattern at the real pitch, its markings engraved at their measured place, its wear where use puts it — and the
colours measured off the most neutrally lit picture. Generators and projection paint what no material imitates.
**Start from a LOOK** (`lune run kit materials --looks [query]`, kit/materials/looks.json; SEE them all built and
baked with a life: `lune run kit materials --looks --sheet` -> build/materials/looks/sheet.png): a real surface's whole
recipe — its base values (a kit finish, a measured material, a scan's measured mean or a labelled estimate: every look
says which), the scan that breaks it up, its micro-pattern at real size, how much its colour varies, which grime it
shows: `a.material("stock", **rbx.look("walnut_wood"), life="used")`, `**rbx.look("powder_coat", color=(0.3, 0.05,
0.04))` — ANY key overridden inside `rbx.look(...)` (passing a look's key to a.material again is Python's "multiple
values" error). 46 looks: the Glock's nitride slide and polymer frame, parkerized, blued, anodized (black, or any
colour on aluminium), brushed stainless, scratched steel, brushed / matte (bead-blasted) / turned aluminium, cast iron, worn brass,
copper, chrome, car paint, powder coat, enamel, ABS, rubber, rubber flooring, rust, rusted steel, oak, walnut,
cherry, mahogany, dark and furniture wood, end grain, bark (fir), oak and mossy bark, leather, bone, skin, concrete,
rock, brick, marble, porcelain, canvas, burlap, cloth, wool, nylon webbing. **No flat colour:** `vary=`
(0..1) moves a material's colour about its own value — a board's tone drifting along it, an oxide's mottling — +-16%
over ~120 mm, +-8% over ~25 mm and a warm / cool drift, object-space (seamless), its average kept (every look has
one). **End grain** (`pattern="endgrain"`, `pattern_mm=` a year, `grain=` the tree's axis): a sawn trunk's or log's
concentric rings and darker heart (`a.zone` the cut face). **Dust:** `grime_tone="dust"` — a light grey-beige in the
recesses, the only grime a dark finish can show (the default dirt is a dark brown that darkens). **Wear where USE
is:** `a.contact("hand" | "rub" | "ground", at=, size=)` — boxes (studs) the bake's wear follows: a hand smudges and
polishes what it holds and wipes its grime off, a holster rubs flats and burnishes edges, the ground gathers dirt and
scuffs where it rests (facts.contacts: each kind's share of the map).
**Markings are engraved, never painted from a lit picture:** each marking at its measured place and size on the
picture (`rbx_trace.px` turns its pixels into design units): `a.cut(<part>, a.text(..., "engraving", depth=...,
facing=...))` — the same metal both sides (projecting a lit render onto metal gave the Silverballer two different
textures). A logo: trace its close-up (`kit trace`) and cut its outline in; a printed or painted mark: `a.decal`.
Code-built surfaces get real detail from SCANS: `a.material(..., scan="Metal008", scan_mix=0.6)` (rbx_scans: the
owner-approved CC0 scans — metal, rust, wood species, bark, cloth, leather, plastic, concrete, rock, bricks; `color` /
`rough` stay the averages; a metal scan's own metal map says where it is NOT metal — rust streaks on steel).
`lune run kit materials --scans` lists them with their real tile size; more is a DOWNLOAD: the owner approves the
exact ids, then `kit materials --fetch <ids>` (size checked against ambientCG's API, sha256 pinned — a re-fetch must
match it —, only ambientCG's hosts over https, maps only) and a VETLOG.md row.
**The map's size comes from the need** (reference/14): sharp enough is one texel a screen pixel where the piece is
judged - 1028 px a metre for a hero piece (0.75 m), 257 for a prop (3 m). A hero / aaa MASTER that names no `tex=`
gets each group's map sized by its surface (2048, or 4096 from two square metres up; the summary says `maps by
need: main 4096`); a size you name is kept. A game version keeps its master's sizes (the kit has seen
Roblox keep a 4096 map: the test upload of 2026-11-12, reference/14); a prop's game build stays at 1024. Every full build's `texel_bar` (a report: listed last) names a group that is blurrier than its
bar and what a larger map would give (`a.group_texture(group, size)`), or that none reaches it (its own `group=`).
**Pattern vs texels:** a real-pitch pattern (`pattern_mm=`: grip texture, end-grain rings) needs 4+ px of map a cell
— gate `pattern_resolution` names one the bake would blur to mottling (more texels: `tex=`, the part in its own
`group=`; or a coarser pitch where the real object allows). A sculpt's (and a dense imported mesh's) UVs follow its
FORM, not its relief (rbx_uvcharts: six charts by the smoothed normal, conformal): a smart projection cut the stump's
bark into islands that left 0.11% of its map on the surface (0.05 px/mm; now 1.19). The automatic UVs' islands are
then PACKED BY THEIR SHAPE (rbx_uvpack: the small ones in the holes the big ones leave; `packed by shape: main 72%
(Blender's 55%)` in the summary, `facts.uv_pack`) wherever that covers more of the map than Blender's packer did.
**Wear in quick rounds:** a build that changes only a material's `life=` word or its wear numbers (`wear`, `chip`,
`grime`, `dust`, `burnish`, `rub`, `smudge`, `vary`) reads its last bake's passes and layers them anew - seconds,
no unwrap, no Cycles (`passes kept: main 6 of 6`; reference/14). Settle the shape, colours and finish first, then
the wear.
**What lies ON the surface: the material's own LAYERS.** The wear keys are the kit's fixed recipes; anything else
that lies on a surface is a layer of that material, written in the order it happened (the last one on top):
`a.material("paint", color=..., chip=0.4, grime=0.3, layers=[rbx.layer("rust", where="chipped", amount=0.8),
rbx.layer("rust", amount=0.15), rbx.layer("soot", where="low", amount=0.3, opacity=0.6)])`. WHAT: a named layer
(`rust`, `moss`, `snow`, `mud`, `soot`: tones measured off the kit's scans) or your own name with `color=` (linear;
`rough=` / `metal=` if it has its own). WHERE it may lie (`where=`): `all`, `edges`, `cavities`, `flats`, `up`,
`low`, `chipped` (where this material's paint chipped) - from the maps the bake already has. HOW MUCH (`amount=`):
the share of that PLACE it covers (a texel where the source is faint counts for less), the likeliest first,
broken up by noise (`breakup=`, `grain="patches" | "fine"`); `opacity=` under 1 is a film the surface shows
through. DIRECT IT BY THE REPORT: per layer the summary says the share of its place that was asked and the share
of the MATERIAL that makes - `layers: main paint rust where chipped 80% -> 5% + rust in cavities 15% -> 3% + soot
low down 30% -> 27%` (a small second number with a large first one: the place is small - ask another place, not
more) - and `facts.layers` the room each place gives; a layer with no place says so (`rust where chipped 50% -> 0%
(nowhere)`: that material has no chips). A layer changed, added or taken out reads the last bake's passes; one
helper pass is baked the first time a group's layers need something no pass holds (a first `up` or `low` layer;
the first layers of a group where no material has a wear number) and is kept when the layers are taken out.
Every layer has its own noise, from what it is and where it lies: adding, removing or moving one leaves the
others' patches where they were. They go on after the material's chips and grime and before its dust, and take
the occlusion's shading of what they lie on; a recipe worth keeping goes into a look (`layers` is a look's key).
HOW THICK it lies (`thick_mm=`, millimetres of the real object): relief in the normal map - a bank at the layer's
edge and a lumpy top, so it reads as a deposit and not as paint. The named layers have their own (rust 0.4, mud
3, moss 6, snow 12: estimates; soot 0, a film), a layer of your own colour is a stain (0) unless you give one,
and `thick_mm=0` makes any layer a stain. What a map can show of it depends on its texels: the summary names the
thickness (`mud low down 50% -> 47%, 3 mm thick`) and says `(too flat to show: 0.6 deg)` where neither the
layer's bank nor its top tilts the surface 2 degrees, and `(too steep for this map: its bank is held at 63 deg)`
where the bank is at the hold - either way the MAP is too coarse for that thickness (more texels: `tex=`, the
part in its own `group=`), not the number wrong. `facts.layers` has each layer's `bank_deg` and `top_deg`.
LIMITS: a layer is ONE tone (none of a scan's variation); its noise lives in the map's space (it can break at a
UV seam); its relief is in the normal map only (the occlusion and the outline do not know of it) and is sized
by the mesh group's AVERAGE texels per millimetre (a part given more or fewer by `a.texel` gets a relief that
much too flat or too steep; without `real_scale()` a stud is taken as 280 mm); `low` is the lower part of its
own mesh group; scratches, patterns and stamps are drawn after it; there is no painted mask yet.
   **Colours:** `lune run kit vision albedo <the traced picture> -o <file>.npz` (Marigold-IID: its colour with the
   lighting taken out, roughness, metalness), then `a.trace_match(..., albedo=<file>.npz,
   regions="refs/<name>.regions.json")` — gate `colour_match` compares the model's colour map with it region by region
   (CIELAB delta E; it says how: "darker by 16 L*", "green where the reference is blue"; build/renders/<name>_colours_<view>.png)
   from EVERY traced view that has its albedo + regions — side, side_left, front, back, top (a.trace_match(view=...)).
**Colours from pictures, ungraded:** before sampling a colour from a reference, `lune run kit refs colour <picture> [--neutral x0,y0,x1,y1] [--sample grip=x0,y0,x1,y1]` — a render or a photo is often colour-GRADED (the owner's Silverballer side render: a blue cast of chroma 8.4 — black rubber sampled as navy). It measures the cast on a surface you know is neutral (else the least colourful mid-tones), balances the picture and gives each sample raw and balanced: build with the balanced one. Choose a measured material by looking: `kit materials --sheet` (all 86 on spheres as rbx.real() gives them).
Real materials: 86 measured substances (physicallybased.info, CC0; `lune run kit materials [query]`); the critic's
`material_values` warns when a material NAMED like one ("gold", "brass", "copper", "silver") looks nothing like it —
use `rbx.real(...)` or name the surface it really has (`painted_gold`, `dark_brass`); steel and iron are not judged
(their finishes range from mirror to blackened). **Physically based values** (`pbr_values`, rbx_pbr — an ERROR at
hero/aaa): metalness is 0 or 1; a metal's base colour is 180-255 sRGB (its reflectance), a non-metal's 30-240 (aaa:
50+). A dark "gunmetal" is never a dark metal — real ones are COATINGS (parkerizing, bluing, paint, anodizing: metal
0); a darker bare metal (150-180) only when rough. Pick from `rbx.finish(...)`: `gunmetal_parkerized` · `blued_steel` ·
`black_anodized` · `nitride` (a pistol slide: near-black, slick) · `painted_metal` (color=) · `enamel` · `pearl_paint` ·
`polymer` · `rubber` · `machined_steel` · `dark_steel` · `brushed_aluminium` · `chrome` · `polished_brass` ·
`cast_bronze`. `satin=True`: a partial metalness on purpose; `pbr=False`: stylised on purpose (listed in facts.pbr).
**What a life does to it — `life=`, on ANY material:** `a.material("slide", **rbx.finish("nitride", life="used"))`,
`a.material("wall", **rbx.real("Brick"), life="used")`, `a.material("x", color=..., rough=..., life="heavy")` — the
wear keys for the surface's class, worked out from its own values (a bare metal; a dark coating: edges burnished to a
satin grey 2.5 mm wide, flats rubbed in patches; a dark polymer / rubber: the same, softer; paint (`under=` given):
chips; a lighter non-metal — wood, stone, fabric: dirt in its recesses and handling marks). `"used"` is the wear the
owner rated on the Glock (85/100); `"new"` · `"light"` half of it · `"heavy"` half again more. Every wear key you also
give a.material wins: `life="used", rub=0.8` (a holster zone). **Dark finishes** (`dark_finishes`, a warning): two big dark non-metals under 15 sRGB apart read as ONE mass
(the Glock's frame at 57 under its 47 slide: "the same blue-navy" to two fresh judges; the rated build: frame 86 —
`color=(0.095, 0.094, 0.092), rough=0.72` — under the slide's 47); on a hero, a big dark finish with no burnish / rub
is named too (eight judges read a bare one as "no wear at all"). **Roughness variation** (`roughness_variation`,
measured on the BAKED roughness map, material by material): a material on 5%+ of the surface that is flat at two of
three scales (fine / mid / coarse) is named — flat roughness reads as plastic; give it `scan=`, `pattern=` (fine) or
`wear=` + `grime=` (mid, coarse). Style: pictures of OTHER objects in the wanted style
(a CC0 pack, the kit's starters, concept art — never the object itself: that is a reference); every full build
reports how close the look (SigLIP 2) and the outline (solidity, fill, aspect vs the style's range) come
(`build/renders/<name>_style.png`). A report, never a gate.
**Surface** is automatic and scale-aware: edge highlight radius and default bevels follow the model's size; wear,
chips and polish land on CONVEX exposed edges (curvature from the baked normal), dirt in concave corners and
crevices. Raise `chip=`/`wear=`/`grime=` per material for a used look; `pattern=` adds micro-relief (hex · weave ·
brushed · grid · coat · engraved). **The sculpt at REAL size:** `pattern="checkering"` (a grip's diamonds), `"knurl"`
(a round part's rolled diamonds), `"stipple"` (punched dimples), `"pebble"` (a rubber grip's bumps) with
`pattern_mm=<real pitch>` — the cell comes from the group's MEASURED texture density, so 20 lines per inch is 1.27 mm
on the model (measured back off the export by `kit library inspect`: test_patterns.py). Take the pitch from a source
(`kit refs dims`), not from a game model (one 1911 model's checkering was 6.2 mm — stylised). Under ~4 px a cell is
too fine for the map (the bake's facts say so: `resolved`): give the part more texture or its own group.
**Engraved:** `pattern="engraved"` — ornamental scrollwork (S-scrolls, a vine,
leaves) with dark tarnish in its grooves, for engraved bronze / chased silver; give it its own material (the plain
trims stay plain). Its grooves shade like relief, so the score counts them as crease detail. **Wood:** `pattern="wood"` — grain along each part's own long axis and a tone per part, so
make EVERY board its own part (small gaps over a dark core make the seams): see the crate and treasure_chest starters.
**Shape right, surface wrong? Paint it from the reference.** When a code-built model's form matches but its surface
reads as flat colour against the photo (a leather wrap, worn two-tone paint, a dark grip on bright steel), TRELLIS.2
paints the asset's OWN last full build from the picture: `lune run kit gen texture <asset> --image <picture>
[--turn <deg>] [--group <g>]` -> `assets/models/<asset>.tex.glb`; then `a.texture_from("<asset>.tex.glb", mix=1.0,
channels=("color", "rough", "metal"))` before `a.build()` bakes it onto the atlas (closest surface; the kit's AO, wear,
grime and edge normals still go on top). `--turn`: stand the object in the picture as the model stands (a trace's
`rotate`). Read `facts.texture_from` (coverage %, mean difference per map) and LOOK at the sheet. Limits: 512 —
colour regions, not lettering or engraving (relief / displace); the unseen sides are guessed; it decides what is metal
(`channels=("color",)` keeps the kit's roughness/metal); albedo, so a lit photo's leather comes out darker; a shape
edit after painting drops the coverage (`texture_coverage` warns) — paint again. Details: kit/gen/README.md.

**Paint it with its references** (rbx_project): when the look IS the reference — a stylised hero piece, an
engraved or painted relic, markings and wear no material imitates — project the traced pictures onto the model and
bake them into its colour map: `a.project("<name>_side")` (+ `a.project("<name>_top", view="top")`, one call per
registered picture). Each picture paints only what its camera sees FIRST (a depth test: a part behind another gets
nothing), fades on faces turned away (`facing=`), never takes the backdrop (the outline's edge, `feather=` px, takes
the colour from just inside), and pictures blend by how squarely a face looks at each. A side picture with the front
on the right paints the right side (+X); front on the left, the left side; `mirror=True` paints the other side
mirrored (lettering reads backwards). Framing is `trace_match`'s: the model's silhouette box (without the trace's
`ignore=` groups) is the outline's box — so fit the silhouette first (IoU >= 0.9), then paint.
**Colour or detail?** The COLOUR mode (default) paints the picture's own colours: right for a flat-lit or albedo
picture whose colours ARE the object's (a painted logo, a livery, a stylised piece drawn flat). A LIT picture (a studio
render, a photo, chart views each in their own light) is the wrong source of colour — its shading and shadows become
albedo: on the owner's hero piece a studio side render + three chart views (mix 0.85, flatten 0.4) left the model
darker and muddier than its own physically based materials. For those use DETAIL mode:
`a.project("<name>_side", detail=1.0, bump=1.0)` — every texel keeps its material's colour and takes only the
picture's fine structure (engraving, seams, filigree, small markings, light-independent: thin features of its LOG
luminance, a morphological top-hat — gradients, big shadows and shadow edges give ~0; normalised per picture, re-centred
so each material's mean stays within a few /255); `bump=` puts the same lines into the normal map (dark = deep);
`detail_px=` the widest feature still counted as detail (default 5 texels). The verdict's `material_shift_255` says
per picture how far it moved each material (measured: the same lit picture moved bronze -37/255 in colour mode, 0 in
detail mode). Detail limits: a dark PAINTED line and an engraved groove read the same (both become darker + deeper);
a shadow's soft edge can leave a faint trace where a line crosses it. One marking only, not the whole picture:
`a.decal("serial", "<name>_side", box=(x0, y0, x1, y1))` (picture pixels; 4 corners straighten a marking shot at an
angle; `at=(u, h)`, `size=(w, h)` in design units, `picture=` a close-up). Limits: the picture's LIGHT is baked in
(`flatten=0.6` takes broad gradients and big shadows out — crude: small shading stays, a dark paint reads as
shadow); only faces some picture sees get its colour (the rest keep the material — add a view or a decal); `mix<1`
keeps the material's scans, patterns and wear under it; roughness and metal stay the material's; the trace needs a
frame (traced without `--rotate` / `--straighten`: turn the picture FILE itself if it lies sideways). The verdict says
per picture how much it covered, whether the picture is still where its trace says (`projection_alignment`: a picture
cropped or edited after tracing) and how the finished model looks from that camera against the picture
(`projection_match`; LOOK at build/renders/<name>_project_<trace>.png: the picture above, the model below).
**Ornaments FROM the reference** (a wing, a crest, engraving: code cannot sculpt them, a generator smears them):
cut the ornament out (`lune run kit vision parts <picture> --text "wing"`, SAM 3; or `vision mask --point x,y`), then
`lune run kit vision relief <cut-out.png> -o assets/models/<name>.relief.npz` (MoGe-2 normals + Depth Anything 3,
integrated; LOOK at build/vision/<name>.relief_preview.png) and build it at its measured place:
`a.relief("Wing", npz, "bronze", width=..., depth=..., pos=..., rot=(0, -90, 0), bend=...)` (both_sides=True: a
bilateral bust from a side profile — it reads as a lump on a head: use a form + displace instead). A part that already
has its big form (a lofted head) takes the picture's fine sculpting with `a.displace("Head", npz, amount, width=...,
pos=..., rot=...)` — call it BEFORE the part's cuts, and no tiny (1-2 mm) cuts on the dense result.

**TRIM SHEETS: one texture a whole family shares** (`a.trim_sheet`, `a.trim`, 2026-11-15; `rbx_trim`). A wall, a
rail and a crate that each bake their own maps cost three textures and read as three sharpnesses. A TRIM SHEET is
one texture of bands - planks, a stone course, an iron edge, a row of rivets - each a strip of one finish that
repeats along its length:
```python
a = rbx.Asset("trim_keep", tex=1024)                          # the sheet is an asset of its own, built first
a.material("planks", ...); a.material("iron", ...)
a.trim_sheet([("planks", "planks", 4.0), ("edge", "iron", 1.0), ("rivets", "iron", 0.5)], studs=8)
a.build()
```
`studs` is how much surface the sheet's width covers: its sharpness (1024 / 8 = 128 texels a stud) is every user's.
Each band lies on its own stretch of the map at that ONE scale (its heights must fit the sheet) and is baked like
any asset. A band is a FLAT strip of one of the kit's materials: its relief (a rivet's dome, a plank's joint) is
what that material's own normal map carries, nothing is modelled on it. If the baked maps do not repeat along
their length, an eighth of the sheet at each end is cross-faded into the sheet half its width on - all four maps
alike - and the build SAYS so (`trim_fade`, a warning): that makes the two ends meet, it does not make a pattern
repeat, and a band with joints or marks across it shows a ghost in the faded eighths. LOOK at
`<sheet>_color_trim.png` before using such a band; a finish that repeats within the sheet's own studs needs no fade.
`trim_tile` fails a sheet whose ends still do not meet. A model that uses the sheet bakes NOTHING:
```python
a.box("Panel", (8, 3.5, 1), (4, 1.75, 0.5), "any"); a.trim("Panel", "trim_keep", "planks", along=(1, 0, 0))
a.box("Cap", (8, 0.5, 1), (4, 3.75, 0.5), "any");   a.trim("Cap", "trim_keep", "edge", along=(1, 0, 0))
```
The PART is laid into the band as a whole: on each of its flat sides U runs along the band at the sheet's scale
(past the map's edge and round again) from the part's own end, and V is the place across the band - the finish is
the same way up on the front, the back and the ends (never turned over; on the back it reads mirrored), and a side
split into several faces (a bevel strip, a window's surround) carries one run of it. `along=` is the way the band
runs (default: the part's longest side); a top or a floor is laid across the part's depth. The group's maps in the
manifest ARE the sheet's files: one upload, one texture in memory for every model that uses it, and the group is
held to the sharpness bar at the SHEET's sharpness. Every part of a group goes into the same sheet (a group is one
mesh, one texture): give trimmed parts a group of their own. `trim_fit` warns when a part's broad sides are over
twice as tall as the band or under half (the finish pulled or squeezed): use a band of that height - a narrow top
is not judged (give a wall a cap of its own in an edge band). Each flat side starts the finish from the part's own
end, so it does not run on round a corner, and a curved part shows a break at every face: a trim is for flat-sided
construction. The manifest records which build of the sheet the model was laid on (`sheet_build`): a sheet built
again with other bands leaves the model's faces on the old ones - build its users again. NOT proven: that Roblox
repeats a texture past the map's edge on a MeshPart was not seen in Studio (no uploaded mesh to try it on).

**A KIT OF MODULES** (`a.module`, `rbx_trim.module_problem`). `a.module((4, 4, 0))` says this asset is a piece of a
kit that snaps on a 4-stud grid across and up (0: its depth is its own). Its box must span a whole number of cells
on every gridded axis and start on the grid - build it from a grid point, so its far faces lie where the next
module begins. `module_grid` FAILS one that does not; the manifest and the model file carry the grid and the cells
(`ModuleGrid`, `ModuleCells` on the spawned asset's folder) for the code that places it.

**A FAMILY THAT SNAPS** (`a.module(grid, family="Hall")`, `kit family Hall`, 2026-11-17; `rbx_family`). A hall's
straight, end, corner, doorway must meet with no seam: where two stand side by side, the cut one leaves on its side
must be the cut the other leaves on its. The build cuts the model a hair inside every gridded side and keeps the
cut, one raster a grid cell, seen from outside (manifest `module.sides`), and puts an Attachment
`Snap<PX|NX|PY|NY|PZ|NZ>_<v>_<u>` at every side cell's middle. `kit family Hall` reads every built module of the
family: each side-cell shape a connector, which MEET face to face (a wall side any wall side - a module turns
about its up - a top only a bottom), and it FAILS on a seam - two DIFFERENT shapes that almost meet, judged by the
width of the step a player sees, not its share of the area (`build_family.py`: walls 0.6 thick against 0.5; walls
of a free depth 0.7 against 0.5). Every cell is cut into one window the same size on every module (a grid cell; a
depth the grid leaves free: 8 studs centred on the side). A one-sided shape against its own mirror (turned 180
degrees onto itself) is only said. A part that is not closed (a card, a pane) is left out of the cut and named.
It writes `build/families/Hall.json` (`meets`: per side cell, the cells it meets; `whole`: sides whose every cell
meets, cell u against cell n-1-u). `--only a,b` names the family's modules (a dropped module's old manifest stays
in the build). In the game, `src/kit/FamilyRules.place` stands module B against A by those snaps (B turned in
quarter turns until its side faces A's), `FamilyRules.meets` asks the table first.

**A MASK YOU PLACE** (`a.mask`, 2026-11-15; `rbx_mask`). A material's layers lie where the MESH says (edges,
cavities, what faces up). Where a thing goes because the DESIGN says so - the scorch round a muzzle, a painted
stripe, moss up one side, a second material over half a blade - place a mask and let a layer name it:
```python
a.mask("stripe", keep=lambda p: 1.0 < p[1] < 1.5)              # a rule on the point (studs, the model's frame)
a.mask("scorch", picture="refs/scorch.png", view="side")       # a picture laid over the model's box
a.material("paint", color=..., layers=[
    rbx.layer("gold", color=(0.9, 0.7, 0.1), metal=1.0, where="mask:stripe", amount=1, breakup=0),
    rbx.layer("soot", where="mask:scorch", amount=1, breakup=0)])
```
A picture is looked at from `view` ("front", "side", "top") and laid over the box of the WHOLE model, the same
for every group (or over the box of `parts=`, and then on those parts alone: its share is said of them):
where it is LIGHT - or solid, with an alpha channel - the mask is on, and its greys are a soft edge: that is the
blend between two materials. `amount=1, breakup=0` lays the layer exactly where the mask is; a lower amount or a
higher breakup lets the layer's own noise eat into it. The build says how much of each group's surface every mask
is on (`masks: stripe on 11% of main`) and each layer's row says what it covered; a layer that names a mask nobody
placed stops the build before anything is baked. A changed picture or rule lays the layers again on the passes
the last bake kept (the build knows a rule by its text and by what it answers at 1,728 points of the model's box:
a change finer than that needs `--rebake`). A picture goes STRAIGHT THROUGH the model: the far side takes it too (a rule can say which
side: `keep=lambda p: p[2] < 0 and ...`). A mask is asked on the layer's own material only, like every layer.
A BRUSH THAT FOLLOWS THE SURFACE (2026-11-17): `a.mask("worn", stroke=[(0.5, 0.1, -0.5), (0.5, 0.6, -0.5)],
radius=0.12, soft=0.5)` - the points the brush passes through (studs, on the model), how far it reaches, the share
of the radius it fades over. Its reach is measured ALONG the surface, over the map's own texels and across a seam
where two islands meet on the model: a stroke down a box's edge paints round it onto both faces, and never
through a thin part to its far face (a picture does). A stroke more than its radius off the model is refused.
Measured: kit/test/python/test_mask_stroke.py (a thin box's far face, within reach as the crow flies, takes nothing).
`a.mesh_maps()` writes the mesh's own curvature, occlusion and material-id maps beside the textures and names them
in the manifest (`mesh_maps`) - to paint a mask over in another tool, or to look at; they are not shipped.
NOT built: painting ON the model with a brush (a mask is a picture from a view, or a rule); a mask that follows
the surface round a corner.

**SEAMS YOU PLACE** (`a.seams`, 2026-11-15; `rbx_seamplace`). The automatic unwrap cuts a part where its faces
turn 66 degrees and packs what falls out: a round handle comes out as a dozen strips, with a step in its grain at
every one. Say where the cut goes and the part is unwrapped along it and nowhere else:
```python
a.seams("Handle", cut=lambda p, q: p[2] > 0.49 and q[2] > 0.49, sharp=60)
```
`cut` is a rule on an edge's two ends (x, y, z in the model's frame: studs, y up, the front at -z) - true where
the seam goes: down the back, underneath, inside a strap. `sharp` cuts every edge of the part that turns more
than that many degrees (a cap off its tube). The build stops when the rule cuts no edge of the part, says the
pieces as they lie on the finished map (`placed seams: Handle 3 piece(s), 33 edges cut`) and FAILS `seam_placed`
when the map is not cut where you said, when a piece is not cut open (a band or a tube laid round on itself, a
ball), or when more than 5% of the part lies stretched. Look at the group's colour map once: the side of a handle
is one rectangle. On every route but two (2026-11-17): a sculpt's part leaves its sculpt charts and is laid along
its cuts; on the high-and-low route's game mesh the part is laid along its cuts, then packed with the rest as a
part that brings its own layout (`build_seam_routes.py`: the handle down the front one place a vertex, down the
back two, as on the automatic route; a placed part is never stacked on an identical twin). A generated mesh still on
its generator's atlas (its paint is laid there), a part that also brings its own layout (`a.mesh(uvs=)`: one or
the other) and a trim-sheet group stop the build; a game version (`kit optimize`) is unwrapped afresh without them. Every island of the group is brought to one scale before the pack: a part without placed
seams keeps its islands and may sit a few percent denser or coarser than without.

**THE BAKE CAGE, SET BY YOU** (`a.bake_cage`, 2026-11-15; `rbx_bakecage`; the high-and-low route). The cage is
how far above the game mesh the bake's rays start before they look back for the high. The kit measures one depth
a group. Set it yourself where that is wrong - deeper where a boss stands proud of its low, shallower in a gap
where a deep cage reaches the next part:
```python
a.bake_cage(2.0, group="face")                   # millimetres, the whole group
a.bake_cage(3.5, group="face", parts=["Boss"])   # these parts alone: the cage takes its own shape there
```
Held three ways. `bake_cage` FAILS when a cage you set is under what its part's high stands off the game mesh
(the rays would start inside the detail) and says the depth it needs. `bake_cage_deep` warns when it is over six
times its need. `bake_misses` sends up to 20,000 of the finished map's texels' rays again and counts those that
found no high - the black patches of a bad bake: over 1% is an error where you set the cage, a warning where the
kit did. A part's copies (a.repeat, a mirror) share its place of the map and its cage. The group and the parts you name must exist: a wrong name stops the build.

**THE FITTED CAGE** (`a.bake_cage("fit")`, 2026-11-17, card urp5). One part can need a deep cage at a proud detail
and a shallow one in a gap beside it - no one depth does both (measured on build_cage_fit.py: a 3 mm dome and a
fin 0.61 mm off a wall; 1 mm loses the dome, the kit's own 4.4 mm bakes 16% of the walls wrong). The fitted cage
is solved like a hand-sculpted one: every point of the high cleared, every face held to under half the room in
front of it, each corner pushed along its own normal.
```python
a.bake_cage("fit")                                # the whole group
a.bake_cage("fit", group="face", parts=["Body"])  # these parts; the rest keep the group's depth
```
`bake_cage_pinch` warns, with the part, where the room stops the cage short of the high (bake that part apart).
EVERY high-and-low bake is also held by `bake_cross`: each texel's ray replayed as Blender casts it - forward from
its start, the NEAREST face either way round, a face seen from behind too (a flipped normal) - against the surface
over that texel. Over 1% wrong is an error where you set the cage, a warning where the kit did; its facts name a
few places (`at`, mm). Read it, not the map: the kit's calm_normals overwrites a flipped texel with its neighbours,
so a crossed wall can LOOK right in the map and smear on a real model. A set cage's need counts the high-only
parts too (a thread, a dome).

**VERTEX PAINT** (`a.vertex_paint`, 2026-11-15; `rbx_paint`). A colour given to the surface by where a point is:
darker toward the ground, one side warmer, a part a shade off its neighbour.
```python
a.vertex_paint(lambda p: 0.55 + 0.15 * p[1])             # a grey by height: 1 = as it is, lower = darker
a.vertex_paint((1.0, 0.92, 0.85), parts=["Grip"])        # a colour, on these parts alone
```
`color` is (r, g, b), one grey number, or a rule on the point (x, y, z in the model's frame, studs, y up) giving
either; several paints multiply. THE ENGINE: Roblox shows a mesh's vertex colours on a part with a plain material
or a TextureID, and - by the reports the kit has, not yet seen by the kit in Studio - NOT under a
SurfaceAppearance, which is what the kit ships. So the paint is laid twice, each where it is seen: multiplied
into the COLOUR MAP at every texel by the rule itself (what the SurfaceAppearance shows: after the kit's chips and
grime, which it tints too, before the dust, and under the material's own layers), and written into the mesh's VERTEX COLOURS in the file (what a part shows that is given the mesh
without its maps). The build says it (`painted: main (Post: 0.25 to 1.00)`), and the exported file is read back
corner by corner against the rule itself: a paint that is not in it, or sits on other corners, fails
`export_read_back`. A game version (`kit optimize`) takes its master's maps - build the master with the same
paint - and writes its own vertex colours. A part on a trim sheet cannot be painted (its maps are its band's): a
paint that names it stops the build, a paint on everything leaves it out. NOT SEEN in the engine: if Roblox does
show vertex colours under a SurfaceAppearance after all, this paint would show twice - one Studio look settles it. A blend between two MATERIALS by paint is a placed mask with a
rule (`a.mask(keep=...)` and a layer): the same thing, at the map's sharpness instead of the mesh's.
NOT built: a brush; a copy tinted a shade off its original in the game (one map, one colour: tint the instance's
SurfaceAppearance.Color there).

**A TILE** (`a.tile`, 2026-11-15; `rbx_tile`). A square of ONE finish whose left edge meets its right and whose
top meets its bottom: laid side by side it covers a wall, a floor or a terrain with no line between copies. In
Roblox that is a MaterialVariant (ColorMap, NormalMap, RoughnessMap, MetalnessMap, StudsPerTile).
```python
a = rbx.Asset("tile_cobble", tex=1024, size=(8, 0.1, 8))
a.material("cobble", ...)
a.tile("cobble", studs=8)        # 8 studs of surface a tile, each way
a.build()
```
The build bakes the finish on a flat square of studs x studs that fills the whole map (the asset's own `size=`
is set from it), makes every map repeat BOTH ways (the normal map made unit again after the fade), FAILS
`tile_seam` when ANY of the four maps as written still steps anywhere along an edge where two copies meet, and
puts `tile` in the manifest: the studs and the four maps' files - what the world lane's material list takes. `trim_fade` warns that an eighth of
the tile at each edge was cross-faded: fine for a finish with no structure (paint, stone, rust, sand); bricks or
planks show a ghost there - look at `<...>_color_trim.png`. NOT built: a tile with modelled relief (bricks baked
from geometry); it is a flat finish.

**A STYLISED LOOK, PAINTED IN** (`a.stylise`, 2026-11-15; `rbx_tile.ramp`). THE ENGINE: Roblox has one lighting
model - no toon or cel shader, no ramp. So a stylised model carries its light in its COLOUR: a few flat tones by
which way a surface faces, drawn into the colour map, and the surface left matt and not metal so the engine's
own light does not model it a second time.
```python
a.stylise()                                    # three tones, the light from above and a little in front
a.stylise(bands=2, shade=0.5, parts=["Hat"])   # lit and shadow, these parts alone
a.stylise(bands=0)                             # a smooth painted ramp
```
`light` is where the painted light comes FROM (the model's frame, y up), `shade` the darkest tone, `rough` the
roughness the painted surface gets (0.9). The build says what was asked and what is on the map (`stylised: main
all in 3 flat tones (lit 2.4x its shade on the map)`) and `stylised` FAILS when the colour map as written does
not carry the light. The kit's own wear, grime and occlusion lie over the tones (a worn piece shows more than
three). A material over 0.2 metal stops the build (it mirrors the real light); under that its metal is set to 0.
Two `a.stylise` on one part multiply. It goes under the material's own layers, with `a.vertex_paint`. The
normal map is left as baked; the model's pose is fixed in the paint - a part that turns in the game (a.joint)
carries its painted light round with it.

**SEE-THROUGH BY DEGREES** (`a.fade`, 2026-11-15; `rbx_cutout`). A part's own transparency is one number for the
whole part; `a.cutout` cuts all or nothing. A FADE says how solid each point is, 0 to 1: a pane clear at its foot
and frosted at its top, the soft edge of smoke, a ghost.
```python
a.box("Pane", ..., "glass", group="pane")                 # a group of its own: the mode is the whole mesh's
a.fade("Pane", keep=lambda p: p[1] / 3.0)                 # a rule: 0 = clear, 1 = solid (the model's frame)
a.fade("Veil", picture="refs/veil_alpha.png")              # a picture: its alpha, or how dark it is
```
The degrees go into the colour map's alpha (`<...>_color_cut.png`); the manifest marks the group `alpha_mode:
Transparency` and `alpha_soft`, and the game gives the part 0.02 of its own transparency: THE ENGINE cuts by the
map's alpha when the part is fully opaque and blends it when it is not (reported; not yet seen by the kit in
Studio). The build says it (`faded: Pane 50% clear over 151 degrees`). A fade that leaves the part solid or
clear over all but a thousandth of it FAILS `cutout`; one that is only clear and solid (a cut) or one degree
everywhere (the part's own transparency) warns `fade_grades`. One fade or one cut a part (a second stops the
build); a cut part and a faded part in one group warn `fade_mixed` - the whole mesh is then blended. A game
version (`kit optimize`) bakes its master solid and carries the fade in its own map. Blended surfaces are
sorted by the part, not by the texel: two faded parts through each other can show in the wrong order.
