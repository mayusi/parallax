<!-- reference for the parallax-3d route card; verbatim from the skill page (2026-10-16) -->

## Stage 3 — 3D draft: generate before you code
**Why:** in a few minutes of GPU per generator (each with the card otherwise idle) a generated draft shows the whole object in 3D before any code
exists — its proportions from every side, what each part looks like where the photos are weak — and for a sculpted
part it IS the shape. Pick by what you have: two to four clean views of the object (a product shot's sides, a chart)
→ `kit gen views` (Pixal3D: the shape lined up with every view — the best start for a real object); one big, clean
3/4 picture → `kit gen <name> --image` (TRELLIS.2); the object as separate pieces → `kit gen parts` (PartCrafter).
Then LOOK at it beside the references and the reference models (`build/gen/` renders; `<name>.gen.json`:
`silhouette_iou` per view; `kit vision similar <render> <photo>`). Use it as: (a) the 3D look-target the code-built
parts must read like together; (b) a proportion check — where the draft, a reference model and the photos disagree,
get a better picture before modelling, never guess; (c) the shape itself for every part whose stack is `generated`.
A generated mesh is one welded surface with soft edges: hard-surface parts with sizes and every MOVING part still come
from code (the shape stage), the draft beside them. Measured so far: a whole gun from 4 chart views (Pixal3D) got the overall
shape right with blobby detail; a 145 px side crop gave a ribbed slab — generate from the biggest, cleanest pictures
you have, and a draft that fails (the wrong object, a blob) has cost 5 minutes: say so in the plan and go on.
**Sculpted or ornate? SCULPT it (a.sculpt) or generate it — never build it from boxes.** Heads, creatures, feathers,
engraving, organic or carved shapes and rich surfaces are where code-built models look like blockouts.
**`a.sculpt` — clay in code** (rbx_sculpt: a signed-distance field meshed by Blender's own OpenVDB into ONE closed,
manifold surface — no boolean can fail, no hole can open). In millimetres at real size, Roblox axes, `mirror="x"` for
symmetry: `s = a.sculpt("Head", "skin", voxel_mm=0.5, mirror="x")` → the big masses first (`s.ellipsoid`, `s.ball`,
`s.box(round=)`, `s.capsule(a, b, ra, rb)` tapered limbs and horns) each with `blend=` mm — the fillet a thumb leaves
where two masses meet → secondary forms as strokes (`s.stroke(path, radii, blend=)`: a brow, a tendon, a root — ROUND
in section) or straps (`s.strap(path, height, thickness, round=)`: FLAT in section — a jaw's rising branch, a
cheekbone's arch, a rib, a strap, a rim; bone built from ellipsoid chains read as tubes and slabs) and
carves (`carve=True`: sockets, nostrils, hollows) → creases (`s.crease(path, width, snap=True)`: wrinkles, lids, seams,
sutures — `snap=True` lays a path drawn by eye ON the surface (`s.on_surface(points, depth=)` for any path): a crease
floating over a dome cuts nothing, and the part's report warns of one) → swell a
region (`s.inflate(mm, where=rbx.sculpt_shapes.Ball(...), falloff=)`) → surface relief at its REAL size
(`s.noise(amp_mm, scale_mm, kind=)`: fbm lumps, ridged crests — rock, bark, hide —, cells domes — scales, warts —,
cracks — plates, cracked earth; `where=` a region) → `s.done(adaptivity=0.2, tris=, smooth=)` (smooth: Taubin passes —
the smooth brush, volume kept; `smooth_where=<a shape>`, `smooth_falloff=` mm for one region). An earlier part — a generated
mesh, a loft, a CAD solid — joins as clay with `s.add_part("Name", blend=)` (consumed, its mirrored twins too) and is
remeshed with the rest as ONE surface, carved and detailed like clay. It must be CLOSED to come back whole: an open
mesh comes back closed but hollowed (the build says what share of its volume became clay — fix it with kit make's
clean first). `mirror="x"`: every operation and its reflection (a shape on either side gets its twin). The voxel is the resolution (default: the longest
side / 400): a feature under 1.5 voxels is lost and the build names it (`sculpt_detail`); detail finer than that
belongs in the material (`pattern=`, `scan=`). Meshes are cached by their operations (build/sculpt: an unchanged
sculpt costs nothing; a 200 mm head at 0.5 mm meshes in ~8 s). **Scored as organic:** the share of what is seen that
was sculpted lets surface detail earn `variety` and colour variation earn `materials` (a stump is one bark, its detail
in the surface — not twenty bolted parts in four materials); `Asset(form="organic")` for an imported organic mesh,
`form="hard"` for a machined sculpt. **The form-match TEACHER:** with a checked reference model (kit library get),
`a.form_match(<model.glb>, height=<studs>, rot=, bar_mm=3)` measures the sculpt's surface against the real one's —
never taking it in — and names where the clay must move: EXTRA / MISSING mm per region and HOT SPOTS (model frame,
mm: "missing at [36, 72, 8] mm: 8.2 mm short") and the MIDLINE PROFILE's landmarks ("midline y 102-108 mm: the
build 15 mm in front of the reference: carve, open or move it back") (facts.deep.form_match). PLACE landmarks from
it, never by eye (a skull's bite plane guessed 9 mm high squeezed its maxilla to "a strip pasted under the cheek";
its vault, which the judges called too big, measured within 2-5% of the real one's slices).
**THE SCULPT RECIPE** (proven 2026-10-11: a pure-sculpt human skull, no generators, fresh judges 28 -> 45, the OWNER
75/100 — example `human_skull`, `assets/models/human_skull.override.py`). In this order, each step checked by a NUMBER
on a fast build (`--geo`, minutes), judges only at milestones:
1. MEASURE the reference model first: `R.load`, `R.landmarks` (bite plane, nasion, chin, zygion, gonion...),
   `R.slice_pieces`, its midline profile. Never place a landmark by eye (a guessed bite plane 9 mm high = "a strip
   pasted under the cheek").
2. BLOCK the forms with primitives at measured sizes (balls, ellipsoids, plates, the part kits); the side outline
   from the MESH: `s.trim_to(R.outline(ref, "side"), "side", min_mm=6)` (no picture trace; holes closed, no staircase).
3. FIT the large forms: `s.fit_to(ref, strength=0.6, smooth_mm=15)` — form_match went 1.7 -> 0.85 mm.
4. CHECK the numbers, never a judge's proportion claim alone: form_match extra / missing, midline gaps, hot spots
   ("cranium too big" was false by 2-5%; the real cause was one guessed landmark).
5. SOFTNESS: form_match `crisp` fold share against the reference's — fine relief at the material's scale closes it
   (`s.noise(0.3, 5, kind="ridged")`: 12% -> 21% vs 22.5%); pinched rims alone do not. Then `done(sharp=True)`.
6. COLOUR from the ALBEDO: `kit vision albedo <photo>` -> `kit materials --tones <photo>.albedo.npz` (a photo's own
   pixels carry its shading: 0.49 / 0.39 / 0.24 "olive plastic" vs the albedo's 0.74 / 0.55 / 0.28); its
   grime_tone (stain for bone / ivory / clay).
7. DETAILS LAST: sutures / seams with `crease(snap=True)`; teeth by type with `dental_arch(gap=-0.8)` (they touch);
   brushes for rims.
8. JUDGE when the method changed: `kit judge <asset> --structural "<what changed>"` (a stalled asset gets no packet
   without it). One build: 3-7 min (a 144-operation skull meshes in ~1 min).
**The reference as NUMBERS** (`import rbx_refmesh as R`; plain numpy, the sculpt's frame in mm): `ref = R.load(glb,
height=, rot=)`; `R.landmarks(ref, {"nasion": ("front_min", 110, 130), "zygion": ("side_max", 95, 115), ...})` —
named points by rule; `R.slice_pieces(ref, y)` — EVERY piece of a slice (a holey scan rastered and closed), for
`s.loft_slices([(y, mask, lo, res), ...])` (a form lofted through the real sections); `R.outline(ref, "side")` +
`s.trim_to(outline, "side", min_mm=4)` — the EXACT silhouette, no picture traced. **Sharp, not melted:**
`s.done(sharp=True)` (dual-contouring corners: a box's edges 0.35 -> 0.01 mm), `edge="chamfer"` on any add / carve
(a flat bevel join), `s.brush("pinch" | "flatten" | "inflate" | "crease", path, radius, strength)` (the sculptor's
second pass, headless), `s.strap(...)` (a flat plate — not for bone bars: a strap arch judged worse), the face's
part kits placed by landmarks (`rbx_sculpt_parts.orbit / nasal_aperture / mandible`). **Surface from data:**
`s.stamp("Rock064", tile_mm=, depth=)` (a scan's height map at real size, not noise); `kit materials --tones
<albedo> --mask <cutout>` (base / cavity / edge colours measured, linear) and `grime_tone="stain"` (aged bone, ivory,
clay). **Fit:** `s.fit_to(ref, strength=0.7)` — a smooth correction of the large forms toward the reference after
meshing, the sculpt's own detail kept. **Weld** overlapping parts: `a.sdf_fuse("Body", ["A", ("Bore",
"DIFFERENCE")], voxel_mm=, fillet=)` (Blender's SDF nodes). **Speed:** a 144-operation skull meshes in ~1 min (per-block
pruning, every core) — iterate on `--geo` builds and the numbers (form_match: SOFT, midline gaps, hot spots); judges
only at milestones: a STALLED asset gets no packet without `kit judge <asset> --structural "<what changed>"` (a panel
of 3). Sculpt toward them round by round: the
skull's own sculpt went missing 1.68 -> 0.72 mm (90th percentile 6.0 -> 2.7) in five rounds. Sculpt the WHOLE form against the traced views
(`a.trace_match` judges a sculpted part like any other), then the details, never the reverse. **Start FROM the
references:** `s.from_traces(side="<x>_side", front="<x>_front", blend=)` — the traced views (kit trace) become the
clay's first form, the photos' visual hull (a chest from its two kit make views matched them at IoU 0.994 / 0.996
in a second), then sculpt into it; `mode="keep"` trims a free sculpt back to the photographed silhouette (one view
is enough to trim; `min_mm=4` first drops the outline's islands, spurs and slits thinner than 4 mm — a keep trim runs
through the whole object, and a skull outline's styloid, seen side-on, left fins of clay under its ears; the part's
report warns when an outline has them). `lune run kit gen <name> --image
<picture>` makes the high-detail mesh WITH its own PBR textures on this PC (TRELLIS.2, offline, ~4 min); the build
script imports it into a MASTER: `a.import_mesh("Body", "assets/models/<name>.gen.glb", height=...)` — then cut the
moving pieces out of it, add joints and code-built mechanical parts, `kit optimize` for the game version. Not happy
with the shape: another `--seed`. (Weapons too: the owner's decision on DINOv3's licence, kit/gen/README.md.)
**Sculpted pieces as SEPARATE parts** (a sword's blade, guard, grip, pommel; a lamp's shade, stem, base): `lune run kit
gen parts <name> --image <picture> --parts <n>` (PartCrafter, offline, ~2 min, untextured shapes) writes one GLB per
part + `<name>.parts.json` — each part's box and triangles, and the `a.import_mesh(...)` lines that put the parts back
in place (`L` = the whole object's longest side in studs; give each part its kit material with `mat=`). Each part is
then its own piece to material, joint or cut. Read the boxes first: a part can come out doubled or as a stray shard.
**A REAL THING, PHOTOGRAPHED (photogrammetry: `kit/tools/photoscan.py`, 2026-11-16; his D-R02).** When the
thing exists - a prop on the owner's desk, a rock, a fire hydrant - photograph it instead of generating it:
`python kit/tools/photoscan.py <photos folder> <name> --size 0.62 --axis height` (a size you know, in metres) ->
`assets/models/<name>.scan.glb` + `.scan.json`. It turns each photo upright by its own orientation flag (a phone's
portrait photo) and refuses photos of different sizes; runs COLMAP (vetted, local, on the GPU: VETLOG 2026-11-16)
- the cameras solved from the photos (matched every photo against every other: no network), depth for every
photo; CUTS THE OBJECT OUT of every photo (kit/vision cutout) and fuses only those points, so the table, floor or
street it stood on is not scanned; a surface through them - then levels it (up from the cameras' own up), turns
its longest way along the kit's length, cuts the surface no point stands on, closes it, scales it to your size,
cuts it to a triangle budget and bakes the photographed colour into a texture. Then it is built like any imported
mesh: `a.import_mesh("Body", "assets/models/<name>.scan.glb", height=<studs>)` in a MASTER script, and
`kit optimize`.
THE CAPTURE decides everything: 30 to 60 sharp photos walking ALL the way round the thing at two or three
heights, each sharing most of its view with the next; the thing TEXTURED (plain paint, glass and chrome cannot be
scanned) and standing clear of what is behind it (the cut-out must find it); one camera at one zoom, held
upright; even light. Held - the tool FAILS (exit 2, its files kept to look at) when fewer than 80% of the photos
are placed, when the cameras' solve is off by more than 1.5 pixels, when photos were placed only in a separate
piece, when the cameras do not agree which way is up, when the base was not photographed and the scale is read from the height (over a fifth of the footprint filled in: the height is short and the scan comes out too large - give --axis width or length, a size across it, or shoot lower), and when the scan SEEN THROUGH ITS OWN CAMERAS does not
cover the object cut out of each photo (an outline overlap under 0.93, or any photo under 0.85). That last one
matters most: 24 small photos of the test urn placed every camera at 0.43 px and still built a doubled shell
round it - only the outline caught it (0.88; the good capture 0.99) - until the cut-outs went into the fusion,
which cured the shell and left the base check to catch the same thin capture's real fault. SAID, not failed: photos leaving more than
120 degrees round the object unseen (its level - and a scale read from its height - is less sure: a half orbit
tilted it 7.7 degrees). Measured on the test capture (32 photos on a textured floor, quality low, about 10
minutes): 90% of the surface within 2.5% of the true height, the sizes within 6% (a base no camera saw shortens
the height the scale is read from: shoot low too). NOT done: small sharp features come back rounded (the urn's
boss, 5% of the surface over 3% off); a shiny or plain object fails; the photographed light is baked into the
colour (shoot in flat light; his D-R03 is the step that takes it out); `--reuse` keeps a run's slow part to redo
the finish. Proof: `kit/test/python/test_photoscan_build.py` (about 20 minutes: a good capture built to a passing
game version, a thin one refused) and `test_photoscan_outline.py` (the outline check against exact answers).

**THE PHOTOGRAPHED LIGHT TAKEN OUT (inverse rendering: `kit/tools/delight.py`, 2026-11-17; his D-R03).** A
scan carries its colour AS PHOTOGRAPHED - the lamp's side light, the far side dark - and in the game Roblox's own
light falls on that painted light again. After a scan passes: `python kit/tools/delight.py <name>` ->
`assets/models/<name>.albedo.png` (the colour without its light), `<name>.delit.glb` (the scan wearing it) and
`<name>.delight.json`. THE ASSUMPTION it rests on: the thing's own colour does not change with the way its surface
faces - so the shading is the part of the photographed brightness the facing explains (9 spherical-harmonic terms
a channel: what a matte surface under distant light shows), divided out; the geometry is never touched.
PROVING IT needs photos under ANOTHER light: `--relight <folder>` - the same thing from the same places (the same
photo names; a tripod), the lamp moved. Mitsuba (vetted, local, GPU) fits the new light for each colouring on some
of those photos and scores the rest, over the pixels the scan covers: the colour with its light out must match them
better, or the tool FAILS (exit 2) and delivers nothing. Without `--relight` it delivers the colour and says NOT
PROVEN - under the SAME light the photographed colour always wins (it IS that light: the first benchmark scored
that, and a light fitted to the visible background made an overfit look like a gain; the review caught it). It
also stops when the scan does not line up with its cameras (the outline, and the photographed colour against each
photo - a mirrored frame keeps a round thing's outline but not its pattern). Measured on the lamp-lit test urn:
under the other light 35% less error on 8 unseen photos (0.078 vs 0.120); a deliberately wrong colour (the lamp's
shading doubled) 0.211 - rejected; the colour's tie to the shading 0.95 as photographed, -0.10 after. NOT done:
shadows one part casts on another and contact darkening (the model knows only the facing - they stay in the
colour); shiny surfaces (matte only); a colour that truly changes with the facing (a pot painted darker at its
base) is partly taken for shading; the light found is coarse (16 x 32) and is not exported; a second lighting from
the same places needs a tripod (photos from new places are not registered). Proof: `kit/test/python/test_delight.py`
(an exact split) and `test_delight_build.py` (about 16 minutes: both lightings rendered, scanned, de-lit, the wrong
colour rejected).

**Licences of generated meshes:** TRELLIS.2 / Pixal3D (`kit gen`, `kit gen views`, `kit gen texture`) are MIT —
fine anywhere. The Tencent-licensed ones (`kit gen omni`, `kit gen mv-shape`, `kit gen paint`, and `kit gen parts`:
PartCrafter's DiT code carries the Hunyuan notice) forbid showing their output outside their territory (not the EU,
the UK, South Korea) — a public game does — so the owner's rule: PRIVATE assets only (`Asset(private=True)`;
`a.import_mesh` refuses their meshes in a public asset).
**Have the reference chart's views? Generate from ALL of them** — one picture leaves the depth and the proportions to
the generator's imagination. Cut each view out (`kit vision cutout <img> --rgba`), then `lune run kit gen views <name>
--view side=refs/<name>_side_rgba.png --view front=refs/<name>_front_rgba.png [--view top=...] [--view back=...]
--ortho` (Pixal3D multi-view, offline): the shape is lined up with every view. Side = the front on the RIGHT (else
`--flip side`), top = the front at the TOP. Read `<name>.gen.json`: `silhouette_iou` per view (the result against
each picture) and `disagreement_pct` (a view whose proportions disagree with the others: fix that picture). Same
import as above; sculpted PARTS too (a stock, a head): cut the part out of each view and generate just it.
A generated piece that came with extras (TRELLIS.2 gave a head with spread wings): `a.import_mesh(..., crop=((x0, x1), None, (z0, z1)))`
keeps a box of it, capped closed. Generate from the BEST picture of the piece: a large 3/4 render of it beats a small
side crop (the side crop gave a ribbed slab; the export guard caught 2 of 3 seeds).
**Steered or from up to 4 views (private assets only — the Tencent licence, below):** `lune run kit gen omni <name>
--image <picture> --from-asset <asset> [--control point|voxel|bbox]` (Hunyuan3D-Omni) generates a shape HELD to your
own code-built blockout's proportions (the blockout's frame in, the mesh back in the asset's frame; the agreement in
its record); `lune run kit gen mv-shape <name> --front <pic> [--left <pic>] [--back <pic>] [--right <pic>]`
(Hunyuan3D-2mv) a shape from up to four views; `lune run kit gen paint <asset | mesh> --image <picture>` (Hunyuan3D-2
Delight + Paint) a texture for a shape you already have. Frames, VRAM and reinstalling: kit/gen/README.md.

**R6 OUTFITS — THE OWNER'S OWN FIT IS THE STANDARD** (2026-10-12: their Diablo fit, measured from its OBJ — studs from
the torso centre; torso ±1 wide, ±0.5 deep, ±1 tall). Layers, inside out: CLOSE layers (trousers, under-sleeves,
shoes) are the R6 block pushed out ~0.013 studs — low-poly boxes, crisp; a JACKET is a fitted box 0.03-0.05 out, 0.5
below the torso (over the hips), its collar 0.4 above; a LONG COAT hangs from the SHOULDERS as ONE garment on the TORSO
(never from the waist, never a piece per leg — "it isn't a skirt, it's part of the whole coat"): a half per side, the
halves meeting at the back centre, open in front, hugging the torso just outside the jacket down to the waist (sides
1.02-1.08, front -0.58, back +0.64), then FLARING below it (sides 1.18 at -0.4, 1.42 at -1.0, 1.70 at -1.6; the back
trailing to +1.0 at the hem) — it stands out round the body and the legs move INSIDE it. Clean low-poly panels (~40
segments a section), a few big folds, no noise. The cloth tools below are for sleeves and baggy trousers.

**CLOTHES (R6 / rigid per body part) — DRAPE, never type a shell** (2026-10-12: the owner called typed box-shells
round an R6 body "really bad"; the same outfit draped by cloth physics bunched, hung and folded like cloth). On R6 there
is no layered clothing: each piece is a rigid mesh welded to ITS body part — put it in a group named for that part
(Torso, LeftArm, RightArm, LeftLeg, RightLeg) and build the R6 body as a `mannequin` group to drape on and to preview.
`import rbx_garment as G`: `G.tube(a, name, mat, centre=, half=(hx, hz), y_top=, y_bottom=, slack=1.3-1.4, p=4,
group=)` (a sleeve, a trouser leg; `t0=, t1=, closed=False, half_bottom=` for a panel — a coat's skirt), then
`G.drape(a, name, colliders=["R6LeftArm"], pull_end=True, end_y=)` (Blender's cloth sim: the top pinned, the end
pulled up so the slack BUNCHES — a sleeve at the forearm, trousers at the boot; ~7 s) or `pull_end=False` for a panel
that falls by gravity onto the legs, then `G.finish(a, name, thickness_mm=, lining="<dark mat>")` (a real wall and a
lining part inside: the dark inside shows at hems and openings). Split a coat's skirt into a half per LEG (it swings
with the stride instead of cutting through it). Rigid details (buckles, zips, boots' soles, a belt) stay sculpts / CAD.
CHECK IT MOVING, by numbers: `G.coverage(a, {"LeftLeg": "R6LeftLeg", ...})` (each body block's faces covered by ITS
group's clothes — bare grey body is a share under 1, with the heights where it shows), `G.clip_check(a, body)` (each
group's clothes swung through R6_WALK: how deep they cut into the OTHER blocks — inside a block it is hidden; between
R6's legs it is not: they touch, so trousers and boots sit FLAT on a leg's inner face, a tube there cut 35 mm into
the other leg and an open inner side showed bare leg mid-stride), and `G.pose(a, G.R6_WALK["stride"])` before
a.build() for a preview render mid-stride (preview only: build the game version at rest).
In game: `Models.wear(character, "<asset>")` (ReplicatedStorage.kit.Models) welds each group to its R6 limb.
