<!-- reference for the parallax-3d route card; verbatim from the skill page (2026-10-16) -->

## Stage 9 — Present and ship
**Fidelity first:** `rbx.Asset(..., stage="master")` builds the no-limits original — every form as real geometry,
2048 maps, no 20k-per-mesh cap and no triangle budget (still enough triangles to carry its forms). The FIRST product
must look its best; the game version is made from it afterwards. A master never ships as built (`kit models` and
`kit upload` skip it, like `private=True`). On a master, `with a.floaters():` detail is the HIGH-QUALITY version: kept
as real geometry in the group it decorates (seat it on / a hair into the surface — it is checked like every part) and
tagged so the game version bakes it; fine recesses (vent ports, screw holes) are its detail too, never a `tiny_cuts`
warning. **The game version:** `lune run kit optimize <name> [--budget <triangles>]` builds `<name>_game` from the
SAME script: every mesh cut to its share of the tier's budget (1.45x the target: under the over-budget line), the
master's full detail baked onto it (high-to-low: normals, AO, colour), the small coloured details that would smear in
the main mesh's map moved to a static `detail` mesh of their own (the summary names every game map as baked: `game
maps: main 2048` - a game map is as large as its master's, up to the 4096 the kit has seen Roblox keep,
reference/14), and the LOSS measured — how far the game surface lies from
the master's (`optimize_loss`: 95% within 0.25% of its length, all within 1.2%) and the reference's silhouette, lines
and look for master and game side by side. A private master's game version stays private. **Presented:**
`lune run kit showcase <name>` renders the last full build under the studio light into build/showcase/<name>/:
poster.png, turntable.gif (it turning once) and mechanism.gif (every joint through its travel in the order the joints
need — `after=` sequences play inside the joint they wait for: the cover opens, THEN the insert lifts out).
`lune run kit upload` → `Models.spawn("crate", {...})` / `Models.tool("rifle", "Rifle")` (PBR maps applied,
anchors become Attachments) · first person: `Viewmodel.new(tool, { offset = ..., arms = true })`.
Uploaded meshes face the right way (the exporter pre-turns them: Roblox's import rotates FBX 180° about Y).
**The conventions, checked by code** (`rbx_conventions`, 2026-11-15) - each was a line in a page before:
- **Names** (`naming`, a warning): a group and a material are named like an identifier - lowercase letters, digits
  and `_`, starting with a letter, 32 at most. The group's name is the spawned part's name in the game. The R6
  outfit groups (Torso, LeftArm, RightArm, LeftLeg, RightLeg, Head) ARE the convention; generated materials
  (`gen_...`) are not judged.
- **The origin** (`pivot`, a warning): the model's origin - where the game places, turns and holds it - lies in the
  model's box or within a tenth of its diagonal of it. Build round (0, 0, 0): a prop stands on it, a handheld thing
  is gripped at it. An R6 outfit (modelled on the body at the origin) is not judged.
- **The normal map** (`normal_convention`, a warning): the bake itself is TOLD the convention Roblox reads (tangent
  space, red +X, green +Y - OpenGL - blue +Z) and the manifest names it. The baked map's own normals (the flat fill
  left out) must be mostly blue: that catches an object-space map or swapped channels; red / green are not judged
  (a one-sided bevel leans them).
- **The normal map's green** (`normal_green`, an ERROR, 2026-11-17): a real surface's slopes add up round any loop;
  read with the wrong green they stop adding up (rbx_conventions.green_reading: the curl of the slopes read as
  OpenGL over the curl read as DirectX). A map that clearly reads DirectX (over 1.67) fails: every bump would light
  from below in the game. It decides only where the map shows it - curved or slanted relief; straight bevels along
  the map's axes show nothing either way, and then nothing is claimed. Measured on the 295 baked maps in build/: 55
  decided, none wrongly, and each of them flipped was called DirectX; scanned material maps decide far more often.
- **The exported file read back** (`export_read_back`, an ERROR): every exported FBX is read back in the same build
  WITHOUT trusting the file's own axis header (Roblox ignores it) and must be the mesh that was exported: the same
  triangles, size and place, every point where it was, not inside out. A file written with other axes, a half turn
  left out, or a hundredfold scale fails. Not seen: the file's unit-scale header (Blender's importer always applies
  it), and Roblox's own importer is not run. It costs well under a second a build.

**What each mesh is in the game** (`rbx_fidelity`, 2026-11-15): every build that exports (not a `--geo` round) CHOOSES, per exported mesh, Roblox's
collision shape and level of detail, writes them to the manifest (`collision_fidelity`, `render_fidelity`), the
model file carries them and `Models.spawn` asks Roblox for them when it creates the MeshPart. The build says them:
`in game: arch PreciseConvexDecomposition / Automatic, ball Hull / Automatic, main Box / Automatic`.
- **Collision** is chosen from what a player would feel - the empty space a cheaper shape turns solid: `Box` when
  the mesh's box holds no empty space a stud across, `Hull` when its convex hull holds none,
  `PreciseConvexDecomposition` when a standing character passes into a space the hull would close (2 studs wide, 5
  tall, a stud deep - or right through a wall thinner than a stud: a doorway, an arch, a room), `Default` for the
  rest. The mesh is read on a grid by rays along the three axes, every face counted in or out, so parts that
  overlap inside one group read as solid. A Tool's parts (nothing collides with, raycasts or touches them) ask for a
  box whatever the build chose.
- **Level of detail**: `Automatic` (Roblox halves the triangles at 250 studs and at 500) unless the simulated levels
  move the surface 1.5 pixels or more on a 1080-line screen at those distances - then `Precise`. A mesh under 64
  triangles is `Automatic`: there is nothing to reduce.
- Say it yourself only when the rule cannot know: `a.collision("main", "box")` for a thing no player touches,
  `a.detail("main", "performance")` for filler. A cheap shape declared over a space a character stands in FAILS the
  build (`collision`); a dear one the mesh does not need warns; a name the model has no group for stops the build.
- A mesh that fails to load in the game is tried again after 2, 8 and 30 seconds, then given up; the spawns in
  between get the grey stand-in and are not swapped afterwards.
- SEEN in Studio (2026-11-18): `CreateMeshPartAsync` with a mesh by its address keeps both settings as asked (Box,
  Hull, Default; Performance, Precise, Automatic - read back off the made part). A mesh made from an EditableMesh
  (the Studio look below) keeps the render setting but turns a Box collision into Hull. NOT proven: the
  level-of-detail simulation is Blender's decimator, not Roblox's; how each collision shape feels under a
  character was not walked.

**Someone else's design** (a game's weapon, a film prop — a study or a pipeline test): `rbx.Asset(..., private=True)`.
It builds and is judged like any asset, but `kit models` never puts it in the game and `kit upload` never sends it
(`kit upload --dry-run` lists what would go): keep its reference picture out of git (`refs/private/`, excluded).

**A glTF BESIDE THE FBX** (`a.also_gltf()`, 2026-11-15). Every group is also written as `<group>.glb` (Studio's
importer and most other tools read it) and named in the manifest (`glb`). The game is still built from the FBX.
Held: the .glb is read back and must hold the group's triangles in a box of the same size at the same place
(`gltf` fails otherwise). NOT checked: its materials and maps as another tool shows them, and what Studio's
importer makes of it (never imported there; unlike the FBX it is not turned beforehand for Roblox's importer).
A shape-only build writes none.

**A PLACE THE GAME VERSION MUST KEEP** (`a.protect`, 2026-11-16; `rbx_optimize`; his D-R08). `kit optimize`
cuts a model to a triangle budget; the decimator keeps what is LARGE and drops what is fine and shallow first - a
sight's notch, a rail's lip, the grooves of a grip. Name such a place in the master's script:
`a.protect("Notch", (0, 1.2, -0.8), 0.15, within=0.004)` - a place (the model's frame), a radius, and how far
the game surface may lie off the model there (default: a tenth of the radius). The decimator then spares the
points inside it until last, and the game build MEASURES there: `protected` FAILS it when the place was lost
anyway, by the place's name and by how much; the summary says `protected: 2 of 2 places kept`. Every `a.socket`
is protected the same way (three quarters of its size round it, 0.1 studs at least): a moving interface keeps
its shape. NOT steered on the high-and-low route (a hand-made low is not reduced: nothing to spare). Measured on the
fixture (fine grooves 0.02 deep, 19,000 triangles to 1,000): steered 0.0014 studs off, unsteered 0.0068.
What it costs: the triangles a protected place keeps are taken from everywhere else (the same fixture at 800
triangles failed `optimize_loss` steered and passed unsteered) - protect little. NOT spared by `--retopo` (a
retopology rebuilds the whole surface): the place is still measured, and fails if it was lost. `hold=False`
only measures. NOT done (his D-R08's second half): the engine's own distance sweep at real scene counts - the
level of detail is still simulated with Blender's decimator; seeing Roblox's needs an uploaded mesh.

**A PHYSICS MATERIAL** (`a.physics`, 2026-11-15). How a group's part slides and bounces in the game - Roblox's
PhysicalProperties:
```python
a.physics("tyre", friction=1.6, elasticity=0.6)     # grips, bounces
a.physics("blade", friction=0.1)                    # slides off what it hits
a.physics("guard", like="bronze")                   # Roblox's own Metal: density 7.85, friction 0.4, bounce 0.25
a.physics("blade", like="Metal", friction=0.1)      # its Metal, but it slides
```
`like=` takes a Roblox material by name (any case) or a word a brief says (iron, steel, bronze, stone, timber,
cloth, tyre ...): the engine's OWN numbers for it, measured in Studio (kit/blender/rbx_physics.py - its Wood is
0.35, not a textbook's 0.7); a number given beside it wins.
friction 0 to 2 (0 = ice, about 0.3 = a plain part, 2 = it grips), elasticity 0 to 1, density 0.01 to 100; what
is left out takes a plain part's. A number out of range or a group the asset has not stops the build. The
numbers go to the manifest (`physics`), the model file carries them (PhysFriction, PhysElasticity, PhysDensity)
and `Models.spawn` gives the part its CustomPhysicalProperties. A spawned model's parts are MASSLESS: density
tells only once the game makes a part heavy again.

**THE FAR STAND-IN** (`a.far`, 2026-11-15). THE ENGINE has its own impostor: a model whose LevelOfDetail is
"StreamingMesh" is drawn as ONE coarse mesh, made by Roblox, while the model is streamed out - a far building or
a tree line keeps its outline for almost nothing. `a.far()` asks for it (`a.far("Disabled")`: it vanishes
instead); the manifest's `far` reaches the spawned model's LevelOfDetail. It tells only in a place with
streaming on, and the kit bakes no billboard of its own. NOT SEEN by the kit in Studio, and uncertain: Roblox
makes a StreamingMesh stand-in ahead of time for models saved in the place - whether one set on a model created
at run time gets a stand-in is not known, and Roblox is replacing the setting (SLIM).

**DRAWS AND OVERDRAW** (2026-11-15; `rbx_batch`). Every build counts what the model costs past its triangles
(`facts.batch`):
- DRAWS: each group is one MeshPart with its own mesh and maps - one draw. A group earns it by MOVING (a.joint),
  by being SEEN THROUGH (a cut-out, a fade, glass: its own mode) or by needing a map to itself. More than four
  solid groups that never move apart warn `draw_calls`: as one group they are one draw.
- OVERDRAW: a BLENDED surface (glass, a fade) is painted over what is behind it. Rays through the model from
  its six sides count the blended faces that face the eye (a back is culled, unless the part is two-sided); over
  four at the 95th percentile warns `overdraw`: fewer, larger sheets, a solid core, or a hard cut-out (not
  blended: sorted by depth, drawn once - it is not counted).
Both are warnings: a splat of leaf cards may be worth its layers. Counted on the parts as built, in the model's
own pose; the engine's real frame cost is not measured here (that needs Studio's own profiler).

**A PART BROKEN BEFOREHAND** (`a.fracture`, 2026-11-15; `rbx_fracture`). A thing that breaks in a game is
modelled broken: its pieces made now, fitted together, each its own mesh, and the game lets them go.
```python
a.box("Crate", (2, 2, 2), (0, 1, 0), "wood", group="crate")   # one closed solid, alone in its group
a.fracture("Crate", pieces=8)                                 # Crate_p1..p8, groups crate_p1..crate_p8
```
Points are scattered in the part's box (the same for the same `seed`) and each piece is the part of it nearer
one point than any other. THE WHOLE STAYS: it is what is seen until it breaks (pieces baked apart never match
each other's wear along the cracks). The pieces are added as groups of their own, baked as if alone (not in the
whole's shadow), and spawned HIDDEN where they fit. In the game:
```lua
local pieces = Models.shatter(model, "Crate", { speed = 14 })   -- the whole goes, the pieces show and fly
```
The pieces come loose, collide, take their weight back and are pushed away from where the whole stood; the list
is the caller's to clean up. Held: `fracture` FAILS when the pieces' volumes do not add up to the part's or one
came out empty; a part that is not closed, has copies, shares its group, is cut out or faded by its map, or
has a hole through it where a crack falls stops the build. A paint, a mask, a shading or a painted light said
for the part is on its pieces too; placed seams are the whole's alone. The pieces are not on the preview sheet
and are hidden in the saved file. Each piece is a draw
and a set of maps once broken: 2 to 24, keep it low. SEEN in Studio with stand-in parts (2026-11-15): the pieces spawn
hidden and untouchable, the whole in front; shatter hides the whole, frees the pieces and pushes each from the
whole's centre. Not seen with real meshes (they need uploading), nor falling in a running game; the cut faces take the part's own material - a broken stone shows stone, a painted crate shows paint inside.

### See it in Studio with no upload (`kit/tools/studio_model.py`, 2026-11-18)

A built model can stand in Roblox Studio before anything is uploaded: its meshes become EditableMeshes and its
maps EditableImages, set the way the game sets them (`kit/lib/models.luau`: size, centre, AlphaMode, the fade's
0.02, the emissive mask, the fidelity settings). In a kit SCRATCH place only, never saved:

1. `python kit/tools/studio_model.py pack <asset>` -> `build/studio/<asset>/` (the meshes, the maps as raw RGBA
   - over 1024 px shrunk and said - and three scripts: `load.luau`, `shot.luau`, `cost.luau`).
2. `python -m http.server <port> --bind 127.0.0.1 --directory build/studio/<asset>` in the background.
3. Through the Studio tools (execute_luau, Edit): `loadstring(HttpService:GetAsync("http://127.0.0.1:<port>/load.luau",
   true))({at = CFrame.new(...)})`. The model stands as `KitStudio_<asset>` - by default high in OPEN AIR (0, 200, 0),
   the sky alone behind it: a model on a baseplate casts a shadow there, which the shot would take for its pixels.
4. THE LOOK IN ROBLOX'S LIGHT: start `python kit/tools/studio_model.py shot --match <place> <dir>` in the
   background, then run `shot.luau` the same way and save the line it returns as `<dir>/look.json` (the Lighting
   as it IS, the camera). The watcher takes the view with and without the model off the screen (the script
   signals its steps in colours; the window must be maximised). Then `studio_model.py twin <asset> <dir>`
   renders the SAME camera in Blender with the kit's Roblox-look rig fed that Lighting -> `pair.png` (Studio
   left, Blender right) and `twin.json`. The camera and the sun come back in the MODEL's frame, so a model stood
   turned about up is shot from its own front and lit from Studio's side. It FAILS when the silhouettes cover each
   other under 95% (the camera, axes, turn or place differ - prove that on a model that is not symmetric: a round
   one matches its own mirror); the light's gap is SAID, the whole twin's (the rig, the .blend's view transform
   and materials). The rig is FITTED to Studio (below): the turned sword 96.9% alike in outline and 1.00 x
   Studio's brightness, the car rim 0.97 (before the fit: 0.69 and 0.66).
5. WHAT IT COSTS: run `cost.luau` (after the shot has finished, ~9 s): 0, 1, 10 and 50 copies laid inside the
   camera's view (each its own cell; `in_view` counts them on the screen), Roblox's render CPU and GPU frame times
   and the frames a second -> the GPU time a copy adds (the sword: 0.0122 ms). Maximise the window first:
   a window behind others is throttled and every number is wrong (its frames-a-second say so).

Engine facts this stage stands on (measured 2026-11-18):
- A MeshPart made from an EditableMesh keeps the vertices where they are given (no centring on its box, unlike
  the importer): the pack writes every group centred, so it stands as the upload will.
- AlphaMode Transparency with the part's own Transparency 0 STEPS a graded alpha into 4 flat bands; 0.02 blends
  it by degrees - the game's fade rule holds. A 0 / 1 cut-out alpha is unaffected.
- Editable meshes and images are NOT counted under Stats' GraphicsMeshParts / GraphicsTexture memory tags: the
  stage measures frame time, not memory (that needs the uploaded mesh).
- Studio's 3D importer (AssetImportService) cannot be reached from the Studio tools, and it creates assets: a
  .glb imported in Studio stays with the uploads.
- The Studio tools' plugin context has `loadstring` and may fetch from 127.0.0.1; a body arrives byte for byte.

### The Roblox look, fitted to Studio (`kit/tools/studio_calibrate.py`, 2026-11-18)

The Blender "Roblox look" (the dressed .blend's two Roblox-look scenes, the look sheet's day / night tiles, the
twin) is no longer assumed: a grey sphere (`kit/studio/calib_sphere.py`, built into build/_calib) was shot in
Studio under 13 Lighting states (`kit/studio/calib_states.luau` + `studio_model.py shot` for each) and the rig
fitted to them (`studio_calibrate.py states <dir>`, `fit <dir> --write` -> roblox_looks.json "_calibration"; a fit
is written only when it is under 6 grey levels off on average, under 15 on every state, and no number ran into the
end of its search). The rule is ONE function, `rbx_lookdev.fitted_light`, used by the rig and the fit alike. What
Studio showed: the sun is white whatever ColorShift_Top says; Ambient and OutdoorAmbient light an outdoor thing as
ONE even colour, the larger of the two; the default sky adds to it by day; at night the moon is weak (0.05 of the
sun) and the night sky lights from the moon's side, near black away from it; Exposure +1 doubles; Roblox's picture
curve is nearest Blender's Khronos PBR Neutral, but Roblox squeezes its brightest light harder (sun and sky: 195
against the rig's 213). Fit: 2.9 grey levels off on average, 3.8 on the states it was not solved on (a night at the
default preset's own values among them: 3.1). Re-run the calibration if Roblox's lighting changes. Not measured: a
place's own Sky, enclosed spaces (Roblox keeps an Ambient floor indoors; the rig's world light is occluded there),
ColorShift_Bottom, specular, Atmosphere, bloom, colour grading.
