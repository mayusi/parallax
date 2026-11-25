<!-- reference for the parallax-3d route card: what makes a surface read as finished - research, 2026-11-12 -->

## What a finished surface needs (research 2026-11-12: sources at the end)

Why this page: the owner's 6/10 on gjallarhorn_anniv was its texture's sharpness, and "flat paint reads as not
textured". This is what studios and Roblox itself say about it, what the kit measured on its own models, what the
kit does about it now, and what is still missing. Rules first; a session follows them without reading the rest.

### The rules
1. **Sharp enough is one texel a screen pixel, where the piece is judged.** More cannot be seen; fewer read as blur.
   A hero piece (held in first person, inspected up close: 0.75 m) needs **1028 px a metre**; a prop past the
   third-person camera (3 m) needs **257** (`rbx_optimize.texel_bar`: a 1080-line screen, Roblox's 70 degree camera).
2. **Do not name a map size on a hero master** unless you mean it: `rbx.Asset(..., stage="master")` without `tex=`
   sizes every group's map by its surface - 2048 as before, 4096 from two square metres up (`maps by need: main
   4096` in the summary, read off the baked file). A size you name is kept as named.
3. **Read `texel_bar` in the build's warnings** (a report: listed last). It names every group that is blurrier than
   its bar and what a larger map would give (`a.group_texture(group, size)`, `Asset(tex=)`), or says the largest
   map its stage gets does not reach it: then the part wants a group of its own (`group=`), never a blurrier
   neighbour.
4. **A game version keeps its master's map size** (the kit has seen Roblox keep a 4096 map; below: "Roblox's
   limit"). `kit optimize` bakes the main mesh's ONE map at its master's size and says what it baked (`game maps:
   main 2048`); every other group gets the size its own surface needs.
5. **Surface in the order a real one is made** (stage 4's keys do each): the clean base material per part
   (`rbx.look`, `rbx.finish`, `rbx.real`) -> its coating or paint (`under=`) -> wear where edges are exposed
   (`life=`, `burnish`, `chip`) -> dirt where air does not reach (`grime`) -> dust on what faces up (`dust`) -> what
   hands and holsters do (`a.contact`, `smudge`, `rub`). Wear is placed by USE, never evenly: a looked-after tool
   that has been used, not a wreck.
6. **Three sizes of variation or it reads as plastic**: big (a tone drifting across a part: `vary=`), medium
   (patches, rubbed flats, stains), fine (a scan's grain, a pattern at its real pitch). The materials must still be
   told apart at 3 m; scratches and dust are for 1 m and are gone by 5.
7. **Shape before maps.** The outline and every seam a hand could feel are geometry; a normal map cannot change the
   outline. Every part gets a bevel of its OWN size (a machined edge is tighter than a cast one): one width for all
   reads as a toy, none reads as paper.
8. **The map is packed by shape for you** (`rbx_uvpack`): the automatic UVs' islands are placed by their real shape,
   the small ones in the holes the big ones leave, and the summary says what that gained (`packed by shape: main
   72% (Blender's 55%)`: the share of the map the faces cover, beside what Blender's own layout covered - more
   texels a metre from the same file). Nothing to ask for. A map that still covers little (`uv_coverage`) has thousands of tiny islands: fewer, larger islands, or the
   small details in a group of their own.
9. **Tune wear, dirt and dust freely: only those numbers changed, nothing is baked again.** A build that changes
   only a material's `life=` word, or how much `wear`, `chip`, `grime` (and its `grime_tone`), `dust`, `burnish`
   (`burnish_mm`), `rub`, `smudge` or `vary` it asks for, reads its last bake's passes and layers them anew - no
   unwrap, no Cycles; the summary says `passes kept: main 6 of 6`. Get the shape, the colours and the finish right
   first (those bake), then settle the wear in quick rounds.

### Roblox's limit: what it says, and what the kit has seen
- SAYS (Roblox staff, 2026-01-30): textures are rendered at up to 4096 x 4096 on MeshPart, SurfaceAppearance,
  Texture, Decal and MaterialVariant where the device has the memory and the view needs it, and smaller elsewhere;
  images are stored as imported up to 8k and served at 4k at most; in Studio it needs Texture Streaming enabled.
  The texture-specifications page says "supports up to 4096x4096" - and, on the same page under UV mapping, still
  "up to 1024x1024 pixel spaces for texture maps".
- SEEN by the kit (the test upload of 2026-11-12; the owner: "Yes, one upload", card v57z): **4096 arrives.** One
  plain grey stripe chart was sent at 1024, 2048 and 4096 through `kit upload`'s own request (Open Cloud, an Image
  asset), each put on a test slab in Roblox Studio (a scratch place) and looked at from close, 13 screen pixels to
  a 4096th of the chart: the 4096 chart showed its one-texel stripes, the 2048 chart its own, the 1024 chart
  neither. The same as `SurfaceAppearance.ColorMap` and as `MeshPart.TextureID`.
- So: `rbx_optimize.GAME_MAP_CAP = 4096` (it was 1024 until that look). A game version keeps its master's map: the
  main mesh as ONE map (it is no longer cut into 1024 pieces), every other group at the size its own surface
  needs; a hero game build that names no `tex=` is sized like a master. Masters: `ROBLOX_MAX_TEX`, as before.
- Two traps that test showed. (1) The plain DOWNLOAD of an image asset (Open Cloud asset delivery) is a 1024 x 1024
  copy whatever was sent, and softer than a native 1024 (its stripes at two thirds of their contrast): never judge
  an upload by downloading it, look in Studio. (2) An image shows for its creator in Studio while its moderation
  is still pending: seeing it is not "approved" (`kit upload --status`).
- NOT tested: a published game on a phone (texture streaming picks a smaller level by memory and distance: 4096 is
  the best case, never a promise), and normal / roughness / metalness maps (only the colour map was looked at).
- The price: a 4096 map is sixteen times a 1024's memory and four maps make a material. The size follows the need
  (rule 1's bar) and is never "the largest": most hero pieces stay at 2048, as their masters do.

### What the kit measured on its own models (2026-11-12, off the manifests of 96 built models, 246 mesh groups)
- The main mesh's texture density: **median 510 px a metre** (a tenth under 208, a tenth over 1187). **76 of 89 main
  meshes are under 1028**, the bar a piece needs when it is held or inspected; 11 are under 257, a prop's. (The
  older manifests do not say which of them are hero pieces, so this is not "76 faults": it is how far the kit's
  usual output is from a close view.)
- `kit optimize` halves every group but the main mesh (coat_hero's coat: 541 px a metre as a master, 273 in game).
- **Half of every map was empty**: the faces covered a median 0.50 of their map (a quarter of the groups under 0.37).
  Packing tighter is sharpness for free: 0.50 -> 0.75 is 22% more texels a metre at the same file size.

### Why the maps were half empty, and what packs them now (2026-11-12, 15 built models opened read-only)
- **Not the pads.** With every island in its own outline plus half a pad, the same islands would cover a median
  0.93 of their map.
- **Not a setting.** Blender's packer by exact shape gives the same cover with any turn as with quarter turns (a
  median 0.001 apart; 13 s a group, up to 222 s); by boxes a little less.
- **The placing.** Blender sets islands down in rows and leaves the holes between the big ones empty. Published
  numbers say the same: Blender's automatic route covers 0.43 to 0.55, a packer that places by bitmap (xatlas) 0.56
  to 0.67 (PartUV, table 6).
- **`rbx_uvpack`** (plain numpy, nothing installed): islands turned onto their smallest rectangle, drawn on a grid
  with every cell they touch, grown by half a pad; the largest placed by exact shape at the first free place, the
  rest dropped into whatever is free; the largest common scale that fits. Islands are turned and scaled together,
  never mirrored or stretched. The guarantee is tested with exact geometry (`test_uvpack.py`) and was checked on
  every layout below from outside (OpenCV at the map's full size): never closer than the 4-texel pad, none off the
  map.
- **Measured on the SAME islands of those models** (33 mesh groups with automatic UVs, as built -> packed by
  shape): the share of the map used goes from a median **0.55 to 0.70** (the emptiest: 0.19 -> 0.39); that is a
  median 11% more texels a metre (up to 43%) from the same file. 30 of 33 groups gained; the others keep
  Blender's layout (the kit's is used only where it covers 3% more). It takes a median 4 s a group (the
  largest, thousands of islands: 20 s).
- Not touched: the high-and-low route's UVs by part (its copies are stacked on purpose) and a generated mesh's own
  atlas.
- **The slow part of every build's UV step is gone** (the same week, the owner's "Yes, layout speed"): Blender's
  packer by exact shape took a median 13 s a mesh group on those models (9 s for the six faces of a box, up to
  84 s) - before the kit's packer even started. The default unwrap packs by BOXES first (a tenth of a second: a
  layout that always exists) and by the kit's packer after. Blender's exact-shape pass runs only where the kit's
  layout is not on the mesh and the boxes may be far from what it can do: the kit's could not be tried (over
  12,000 islands, it raised, its layout did not read back) or it found nothing fuller on a group of more than 64
  islands. To be allowed that, the kit's packer had to be at least as good everywhere: a LONG island (a barrel's
  strip) may now lie on the DIAGONAL (it capped the Gjallarhorn's game body at 0.59 of its map, where Blender,
  turning freely, reached 0.68: 0.70 now); a small set (128 islands or fewer) is packed by a second ordering
  too; a search that starts too full comes down to what fits (thousands of islands on a small map); the scale is
  bracketed to 0.4% (0.6% for a large set). Measured with the very call the builder makes, on the 32 groups:
  never under Blender's exact-shape layout (the least 0.002 over it, a median 0.12; a median 0.70 of the map
  used against 0.56), 157 s in all where that pass alone took 644 s; every layout checked from outside. Against
  the route before (exact shape, then the kit's where it was 3% fuller): the same median, single groups between
  0.016 under and 0.022 over (the scale search lands a hair differently). On the kit's fixtures the UV step of a
  three-box piece went from 27.8 s to 2.1 s. The summary's first number is the kit's layout, the one in brackets
  what Blender's boxes covered - not what its exact-shape pass would have. A fuller layout is always kept; the
  summary only says so from a gain of 3% (a tile's two squares pack 1.6% fuller: kept, and no news).
- **A thin part keeps its own colour (2026-11-13).** A bake gives a texel to the face that covers its CENTRE. The
  packer started every island on a texel's edge, so a strip under half a texel thin - the wall of a 2 cm seam on a
  64 px map, a 1.5 mm lip on a game version - covered no centre at all and was drawn in whatever a neighbour's
  margin left there: dark or grey by the luck of the layout. It showed as a red self-test: the fixture with a
  seam, a groove and a slot lost two stretches of its seam when the layout moved by half a percent (20 of its 35
  islands had no texel of their own - before that change as well; it had passed by luck). Now an island is laid
  in the MIDDLE of the texels its box takes, along each axis (`rbx_uvpack._centred`): a strip thinner than a texel
  that is an island of its own and lies straight has its one row, and an island's box has all its centres under
  it (but for one a hair - under 0.2 texel - over a whole number of texels: it stays at the edge and has all but
  the last). It takes the same cells (they are counted from its size, as before), so no layout is less full for
  it. On that fixture: 0 of 35 islands without a texel; a review's 40 random layouts at 64 to 4096 px: 0 of 122
  thin strips without one (42 before), the same cover. What it cannot do: a part thinner than a texel still has
  ONE texel across - its colour, not its shading; a thin feature INSIDE a larger island lands where that island's
  middle puts it (as much luck as before); an island laid on the diagonal is not helped; nor is a map over 1024
  whose side is no multiple of 1024. Those need a larger map or a part of its own.

### A material's wear changed: the passes are kept (2026-11-12)
- **How studios work**: the maps that come from the MESH (occlusion, curvature, position, which way a face looks)
  are baked once; wear, dirt and dust are layers computed from them, and changing a layer never bakes again
  (Substance Painter's mesh maps and its mask generators).
- **What the kit did**: it already layered its wear in numpy after the Cycles passes - but kept none of them. One
  wear number changed and the whole group was unwrapped and baked again.
- **Now**: a group's passes (colour, the packed one-number channels, normal, occlusion) are kept beside its bake
  cache with the UVs they were baked on (`build/models/bakecache/<obj>.passes.npz`: 3 MB at 2048, 9 MB at 4096 for
  the fixture; a real piece's detailed maps deflate less). The wear numbers are no longer inside them: each material's share of every texel is baked instead
  (`matcov_<i>`), and a wear channel is the numbers times those shares. A build whose passes would be the same
  puts the UVs back, reads the passes and runs only the layering. A pass the file lacks (a layer turned on for
  the first time) is baked alone and added.
- **Measured on the kit's fixture** (the same shapes at three map sizes, unwrap + bake): 1024: 7.2 s -> 1.3 s;
  2048: 17.3 s -> 5.5 s; 4096: 64 s -> 29 s (there the numpy layering itself is 25 s: the next thing to speed
  up). A model with thousands of islands saves its whole unwrap too.
- **The same maps**: a build from kept passes is a fresh bake of the same numbers - byte for byte on the fixture
  (`test_relayer.py`: eight cases - all kept, one pass added, another shape, switched off). The only room between
  them is Cycles' own: its normal pass does not always repeat itself to the bit (a fresh review measured 3 of a
  million texels one level apart between two FRESH bakes), and a kept pass is the first bake's. Against the
  builder before this change, nine fixtures' maps differ by one level of 255 at most, on under 0.1% of their
  texels (a blended edge texel's rounding).
- **The life word too** (the same day, the owner's "Yes, life next"): `life=` sets `wear=`, and wear's mottle was a
  colour ramp and a map range in the material's NODES - baked into the colour pass, so the knob everyone uses
  baked everything again. The mottle is laid on the passes now (`rbx_wear.mottle`: the same noise, baked as its
  own channel; the same ramp in linear light; the same rise in roughness), before anything else reads them. A
  changed life word keeps every pass (`test_relayer.py`); from `new` to `used` only the mask pass a first smudge
  layer needs is baked. Against the builder before it, on the kit's fixtures and a review's probes: the colour
  and the roughness a mean 0.1 to 0.4 of a level of 255 apart, 99.9% of texels within 6 levels, a handful up to 11
  on a bright scanned metal (the noise and the colour are each rounded to 8 bits before they meet, where the
  nodes worked in float). Two things a fresh review found and what
  was done: a BRIGHT colour under a scan or a grain goes past 1, and the nodes darkened it before the pass clipped
  it (a worn aluminium came out up to 57 levels darker) - what lies over 1 is baked as its own pass now
  (`colorover`) and put back first; an IMPORTED mesh's life word never mottled it (its record only carries the
  wear for its chips and grime) and still does not. One difference is left and small: a very smooth material under
  a scan whose roughness dips below 0 gets its mottle added after that clip, not before (the probe: 11 levels on
  0.03% of texels). The normal map moved by a level on 9% of its EDGE texels on the look
  shelf (a few by up to 7; flat faces not at all): the rounded-edge pass is a 64-sample estimate, and other nodes
  in a material reshuffle its noise - two bakes by the same builder still agree. Unbaked previews (the blockout
  and geometry views) no longer show the mottle: it exists on the baked maps only.
- **The layering itself, faster (2026-11-13, the owner's "Yes, layering speed").** With the passes kept, the numpy
  layering was what a wear change waited for on a large map. Four things, each proven to give the SAME BITS as the
  form it replaced (`test_wear.py` SameBits, `test_pbr.py` TestOneZone): the noise fields interpolate each grid row
  once along x and mix two rows per texel row (`rbx_wear.fbm`: 2.5 s -> 0.6 s a field at 4096), not four gathers
  of the whole map; the roughness and the metalness run as ONE channel when their three are the same (every step
  did the same sum three times) and the colour as a contiguous RGB array (`rbx_wear.one_channel`); the packed
  channels are split without `np.repeat`'s copies; the roughness check's same-zone map counts the zone map's
  steps with two summed-area tables (`rbx_pbr.one_zone`: 2.1 s -> 0.55 s) where it compared 289 shifted copies.
  Measured with the kit on its test piece, old and new layering on THE SAME kept passes: the four maps the same
  bytes at 2048 and at 4096; the layering 5.1 s -> 3.1 s at 2048 and 28.1 s -> 15.9 s at 4096; the texture step
  of a build that only changes the wear numbers (wear, chips, grime, dust and the life word at once) on a 4096
  map 36.9 s -> 26.3 s (at 1024 it was under a second already). What is left of those 16 s is spread thin over
  some twenty steps (blurs, masks, the map's own conversions): no single large one. That test piece has no
  hand marks, contact shadows, patterns, stamps or projections: for those the review read every write into the
  roughness and the metalness (each one channel or a plain number) and the relayer tests and the self-test
  build them.
- **A material's own layers (2026-11-13, the owner's "Layered materials").** How a texture artist builds a
  surface: the base, then one layer per cause, each a surface of its own shown through a mask computed from the
  mesh's maps (Substance Painter's fill layers under mask generators: curvature for edges and cavities,
  occlusion, the position for a gradient, the world-space normal for what faces up, a grunge to break it up).
  The kit had those masks, but only inside its fixed recipes (chips, grime, dust). Now a material takes a list:
  `layers=[rbx.layer("rust", where="chipped", amount=0.8), rbx.layer("soot", where="low", amount=0.3)]`
  (`rbx_layers`). A layer is a tone (five named ones, measured off the kit's own scans - rust 0.266 / 0.074 /
  0.022 linear at roughness 0.78 from Rust009, moss from Moss002, snow from Snow006, mud from Ground108 / 111;
  soot is carbon black's 0.04 - or any colour given), a place (`all`, `edges`, `cavities`, `flats`, `up`, `low`,
  `chipped`) and an AMOUNT that means something: the share of its place's room (a texel with a faint source
  counts for less), the highest-ranked first - so "more rust" is one number, the same at any map size. Every
  layer has its own noise, seeded from what it is and where it lies (not from its place in the list), so adding,
  removing or moving one moves no other. A layer takes the occlusion's shading of what it lies on (rust in a seam
  is as dark as the seam). The report says, per layer, the share asked and the share of the material that makes.
  Nothing of a layer is in a render pass: a layer changed reads the kept passes (the kit's test piece: the texture
  step 1.3 s). One helper pass is baked the first time a group's layers need what no pass holds - a first "up"
  or "low" layer, or the materials' coverage where no material has a wear number - in a pack of its own, so no
  other pass is baked again; and a kept record now carries the passes its last build did not read (six at most),
  so layers taken out and put back bake nothing. Proven on that piece (`test_layer_stack.py`, 14 cases of real
  builds): a changed layer's maps are a fresh bake's; the last or the FIRST layer taken out changes only the
  texels it lay on and no other layer's row; a build with no layers gives the bytes it gave before (the committed
  builder against this one on the same kept passes, 1024 and 2048). One fresh review, fixed once - it found the
  noise seeded by list position (a removed layer moved the others), a baked pass my page denied, layers on a
  floater's material silently dropped, a layer erasing the occlusion's shading, and an amount that was not the
  share it said. NOT built: a layer is one tone (none of a scan's variation); its noise lives in the map's own
  space like the kit's wear (not in millimetres: it can break at a UV seam); "low" is the lower part of its own
  mesh group; scratches, patterns and stamps are drawn after it; the kit's own recipes keep their fixed order;
  no layer reads a painted mask yet.
- **A layer has a thickness (2026-11-13, the owner's "do both").** Flat colour reads as paint: what makes a
  deposit read as a deposit is its relief. A layer takes `thick_mm=` (millimetres of the real object; the named
  ones have an estimate of their own - rust 0.4, mud 3, moss 6, snow 12, soot 0 - labelled as estimates: no scan
  carries a real height). Its height is its mask times its thickness with a BANK (full where the mask passes a
  third of its soft edge: a deposit is not a dome) and an uneven top (broad lumps twice its thickness across
  with a ripple half that size on them, never under three texels); the layers' slopes add - millimetres of
  height per millimetre of surface, from the group's measured texels per millimetre - and tilt the tangent-space
  normal in the normal's OWN frame (reoriented normal mapping: on a bevel the relief leans from the bevel), their
  size held to 63 degrees. A layer that reaches its material's border does not end in a cliff there (the height
  is carried a texel over the border before the slope is taken). Measured on the kit's test piece (0.79 px a
  millimetre): rust 0.4 mm in its chips - bank 9.7 degrees, top 8.0; 3 mm of mud - bank 46.8, top 8.0. Two
  numbers, because one over the whole layer is the top's alone and cannot tell a bank from a dome (my first
  report did exactly that). The report names each layer's thickness and says "too flat to show" where neither
  reaches 2 degrees and "too steep for this map" where the bank is at the hold. Proven there
  (`test_layer_stack.py`, 19 cases of real builds): a stain (`thick_mm=0`) leaves the normal map a build without
  layers gives, to the byte; a thickness changes the normal map only - the colour, roughness and metalness the
  same bytes - and only where a layer lies or on the texel beside it (the foot of its bank); the relief is
  raised, not sunk (the normal leans away from where the layer rises, on the built maps); twice the texels a
  millimetre draw a steeper bank; a thickness changed reads the kept passes. One fresh review, fixed once: it
  could not break the sign or "a stain is byte-identical", and found the hold at 70 degrees on a diagonal, one
  number that judged the layer's shape and not the map, a relief turned 117 degrees on a bevel, a cliff along
  every border a layer reached, and my built-map tests blind to a flipped sign. NOT built: the relief is in the
  normal map only - the occlusion, the roughness and the outline do not know of it; it is sized by the mesh
  group's AVERAGE texels per millimetre (a part with its own density is off by that factor; without a real
  scale a stud is 280 mm); the bank's width follows the mask's soft edge in texels, not the thickness.
- **What still bakes**: a new shape or map size, a colour, a scan, a finish, `under=`, a pattern, `real_scale`,
  the surface settings - anything the passes hold. A model whose mesh comes out in another order between two builds (Blender's booleans
  can do that) bakes again and says so in the report's `bakes.why`. A projection's helper passes (float) are baked
  each time. Not kept at all: game versions (their maps are the master's,
  transferred), the high-and-low route, a generated mesh's own atlas, a group of more than 18 materials (2 of 123 built models).
  `KIT_RELAYER=0` turns it off.

### What changed in the kit (2026-11-12)
- `rbx_optimize`: `ROBLOX_MAX_TEX`, `GAME_MAP_CAP`, `texel_bar(quality)`, `map_for_area`, `map_to_reach` (pure, tested).
- A hero / aaa master without `tex=`: each group's map sized by its surface (`facts.map_by_need`).
- Every full build: `texel_bar` and `facts.texel_bar` per group (density, bar, map, what a larger one would give).
- `kit optimize`'s summary names the game maps it baked.
- The passes kept (the same day): `Asset._raw_open` / `_bake_pass(key=)` / `_raw_close`, `facts.passes_kept`, the
  summary's `passes kept:`, the report's `bakes.relayered`; `wear=` out of the material's nodes
  (`rbx_wear.mottle`, the `wearfac` pass).
- Packed by shape (the same day): `rbx_uvpack`, `facts.uv_pack[group]` (Blender's cover, the kit's, which was
  kept), the summary's `packed by shape:`.
- 2026-11-13: `rbx_uvpack._centred` (an island over its texels' centres); `rbx_wear.fbm`, `rbx_wear.one_channel`,
  `rbx_pbr.one_zone` (the layering, the same bytes in about half the time).
- 2026-11-13: `rbx_layers` and `a.material(layers=[rbx.layer(...)])`, `facts.layers`, the summary's `layers:`;
  `thick_mm=` (a layer's relief: `rbx_layers.height / slopes / raised`, each row's `tilt_deg`).
- After the test upload (the same day): `GAME_MAP_CAP` 1024 -> 4096. The self-test's 2048 master now gives a game
  version with one 2048 map at its master's sharpness (8540 px a metre against 8523), where the cut into 1024
  maps had left its one large part at half (4522).
- Cost: a 4096 map is four times a 2048's file and bake (the self-test's four-square-metre slab: 62 s for the whole
  build, 25 s at 2048). That is why the size follows the need and is never just "the largest".
- 2026-11-17, **specular occlusion** (the owner: "New pieces only"): Roblox's material has no specular-occlusion
  input, so a bright environment reflection showed deep inside a slot or under a guard. The bake now takes a
  crevice's reflection down where the occlusion map is dark (`rbx_wear.spec_occlusion`: from occlusion 0.85 down
  to 0.25, roughness up to +0.3 and metalness down to half). A new piece gets it; every piece built or scripted
  before that day (`kit/blender/spec_occ_before.json`) and the kit's fixtures bake as before, byte for byte.
  `rbx.Asset(..., spec_occlusion=0..1)` overrides either way (an older piece gets it only if its script asks).
  Said in `facts.spec_occlusion` (strength, why, the share of each object's texels it touched). Proof:
  `test_spec_occ.py` (the math, the on / off decision, and a real bake of a slot: 33% of its texels rougher).
- 2026-11-17, **noise on the model, not the map** (H6; the same rule: new pieces only, `rbx_wear.built_before`):
  every noise field the bake draws - the grunge that breaks wear into patches, a chip's ragged shape, smudges,
  worn flats, each layer's patches and its uneven top - was drawn across the TEXTURE, so it jumped at every UV
  seam (a patch of soot ended in a straight stepped line along an island's edge). A new piece's bake draws it at
  each texel's own place on the model (`rbx_wear.uv_positions`: the bake's UV triangles rasterised with their
  corners' places; `fbm3`: the sculpt's seeded Perlin at those places, spread like the map's field, a feature as
  many millimetres across as it was texels at the map's own sharpness); each island's places are carried 16
  texels into its margin (left at the field's middle, every seam drew a hairline - seen and fixed).
  `rbx.Asset(..., noise_3d=True | False)` overrides either way. Proof: `test_noise3.py` - a sculpted ball under
  soot the noise alone places: across the map its seams jump 71.6 levels against 8.1 across any other edge; on
  the model 13.9 against 14.4. Cost: about 7 s more on a 512 map (one 3D field a noise call).
- 2026-11-17, **patterns on the model** (H6 / S3: his "lathe_rings, brushed, car_paint, radial_dust"):
  `a.material(pattern="lathe", pattern_mm=, pattern_axis=("Z", centre_mm))` - turning marks, a ring every
  pitch round a REAL axis (a wheel's face, a turned knob); `pattern="flake"` - car paint's flakes, each tilted its
  own way; `pattern="brushed", pattern_axis="X"` - the streaks run along that direction on the model (without an
  axis: the map's rows, as before); `rbx.layer(..., where="radial" | "radial_out", axis=)` - a layer by distance
  from an axis (brake dust from the hub out). All drawn at each texel's place (`rbx_wear.pattern3`,
  `radial_field`), so they run on over every seam; turned into normal-map slopes along the map's own directions
  like every pattern; held by the same pattern_resolution check (4 texels a pitch). Proof: `test_pattern3.py`
  (rings crest and groove all the way round, streaks along their axis, flakes; a real bake: the turned disc's
  normal turns 12.5 degrees across its rings and 1.5 along one, the brushed panel 0.87 across its streaks and
  0.04 along, the hub darkest at its centre). Looked at: the four parts' front view.

### Not built yet (each its own stage; none needs a model made to prove it)
- **Fewer, larger islands** (the packer places what the unwrap gives it: the automatic unwrap still cuts a
  detailed part into hundreds of islands) and the UVs by part's own packing (its copies are stacked: a packer that
  keeps a stack as one island).
- **A look at the other maps and at a phone**: normal / roughness / metalness at 2048 and 4096, and what a
  published game shows on a low-memory device (each needs the owner's go-ahead: an upload, a publish).
- **The other lanes' caps** (effect textures, world atlases, UI art): none was changed by this test.
- **The rest of the layer stack** (`layers=` and its relief are built, above): a painted mask off the model sheet,
  noise in millimetres, the kit's own recipes placed freely in the stack, a relief the occlusion knows of.
- **Ornament as real relief** (H4) and **Roblox's own light in the look pictures** (H7).

### Sources
- Adobe, Substance 3D Painter: baking mesh maps; the Mask Builder and Mask Editor generators (what reads them):
  https://experienceleague.adobe.com/en/docs/substance-3d-painter/using/baking/mesh-map-settings ·
  https://experienceleague.adobe.com/en/docs/substance-3d-painter/using/effects/generators/mask-editor
- PartUV: Part-Based UV Unwrapping of 3D Meshes (table 6: efficiency of Blender, xatlas, Open3D):
  https://arxiv.org/abs/2511.16659
- Roblox staff, DevForum, "4k Texture Rendering", 2026-01-30: https://devforum.roblox.com/t/4k-texture-rendering/4316229
- Roblox, texture specifications (read 2026-11-12): https://create.roblox.com/docs/art/modeling/texture-specifications
  (colour RGB, normal maps OpenGL tangent space, roughness and metalness one 8-bit channel; 256 px for a 5-stud
  object, 512 for 10, 1024 for 20).
- Respawn's texturing of Apex Legends (a base-material library, value charts, checked in the game's own light):
  https://www.adobe.com/products/substance3d/magazine/apex-legends-texturing-battle-royale-phenomenon-2019.html
- Weapon breakdowns (layer order, wear by use, reading at distance, texel density for first person):
  https://80.lv/articles/breakdown-how-to-make-a-weapon-look-realistic-and-eye-catching ·
  https://80.lv/articles/weapon-art-plasma-akm-production-breakdown
- The one-texel-a-pixel bar is arithmetic, not a citation: lines / (2 x distance x tan(field of view / 2)). The two
  distances (0.75 m, 3 m) are the kit's own choice (`rbx_optimize.SEEN_M`): change them there, with a reason.
