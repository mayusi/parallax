<!-- reference for the parallax-world route card; verbatim from the skill page (2026-10-16) -->

## The workflow (blockout ~10 min, a playable lit arena ~30 min)
0. A game? It lives in `games/<Name>/` (`kit game new` / `kit game use`) — its worlds go to its `assets/worlds/`.
1. `kit new world <Pascal> [--from BattlegroundsArena]` → `assets/worlds/<Name>.json` + `<Name>.brief.md`: ASK THE
   OWNER its questions first (the source and its landmarks, routes, scale, the parts plan).
2. Terrain (optional): `kit world terrain <Name> [--size 512 --seed 3 --relief 60 --erosion 60000 --from <image>
   --flat x,z,r]` → `assets/worlds/terrain/<Name>.hm.json` + a shaded relief + `<Name>.paint.png` — LOOK at both, then
   a `heightmap` terrain op (below). How land is made (in order): gradient noise (+ `--warp` studs) or a `--design`;
   RIVERS `--stream 80 --streamK 0.015` (stream-power incision at two scales: major valleys hundreds of studs apart,
   then gullies — ranges with branching valleys and sharp ridges instead of noise cones); `--thermal 40` (slopes
   collapse to their talus angle, also after the rivers); droplet `--erosion 300000` (brush erosion: gullies, fans,
   and the flow + deposit maps); then the PAINTER writes a role per cell from what the land did — channels mud, wet
   hollows lush, fans dirt, cliffs rock / dark cliff, scree aprons under them, a noisy snowline, a sandy shore
   (`--snowline`, `--shore`, or the design's `"paint": {"snowline", "shore"}`). Designed shapes stay as designed:
   basin / plateau (with its edge) / ramp (with its shoulders) / hill cores are re-imposed after erosion (`"keep":
   false` lets the water have one); `"anchor": [x, z, height]` pins one spot (the lake bed) so a re-run never floats
   the map under the water and the buildings; `"terraces": {"step": 14, "sharp": 0.35}` = rock strata on rim / ring.
   REAL-LIFE look = real data: scanned surfaces (ambientCG 1K, `kit materials --fetch <ids> --res 1K`; the viewer
   draws them as PBR with height-blended borders) and SCANNED MODELS (Poly Haven CC0, vetted by hand, VETLOG) listed
   in `assets/worlds/imports/<set>.json` → `kit world import [<set>]` (`"split": true` = a scanned set becomes single
   rocks, `"maxTris": 20000` = fits a MeshPart, textures as 1024 PNGs) → use the names in scatter / forest `"meshes"`
   and in `rocks` (`"meshes"` = scanned crags, `"spireMeshes"` = a tall scanned rock face per spire). Stylised packs
   (Quaternius) are fine for stylised worlds, never for a realistic one.
3. Blockout with the generators; `objectives` (where fights / goals are) and `checks` in the blueprint.
4. `kit world check <Name>` → `build/worlds/checks/<Name>.png` (reachability, exposure, camera, open room, sightlines).
   Errors: spawns that cannot meet, unreachable objectives, TRAPS (get in, never back). LOOK lint (warnings):
   parts that float or lie buried, trees through buildings, rocks / trunks on a road or trail. (Scatter, forest,
   rocks and cover keep off every road laid EARLIER in the blueprint by themselves: put roads first.) Warnings: unreachable
   platforms (named with bounds + height), unfair spawns, cramped camera, little knockback room.
5. `kit world look <Name>` → `build/worlds/look/<Name>/pages/`: ONE PAGE PER STATION at 1920 x 1080 - what the
   player sees at every spawn (Roblox's camera behind the R6 rig), the blueprint's own `views`, the view back from
   each objective, an establishing shot - labelled, each under the reference still it is judged beside (same
   framing, full size). Which still goes with which station: `assets/worlds/refs/<Name>/stations.json` (`ref`,
   `ref_shows`, `ref_crop`, `"ref": "none"` + why, `never`); a station it does not name is paired by order and its
   page says so. `build/worlds/look/<Name>.png` is the index sheet. Open every page.
6. `kit world` → `src/world` (Workspace.KitWorld) + the build; its last lines are `LOOK: <folder> - what is in it`,
   and a world the build changed is rendered there and then (`--no-look` skips it). Then `kit world studio <Name>`:
   the same stations in Roblox Studio's own light, in the kit's scratch place (nothing saved, nothing uploaded:
   plain parts and light, the blockout standing where each mesh will) -> three panes a station (reference, Blender,
   Studio; `build/worlds/studio/<Name>/pages/`). Blender's light is a stand-in: GothicCourtyard's court read navy
   in Blender and near black in Studio, its rooms cold in Blender and orange in Studio (2026-11-12). Walk it in
   Studio (`character_navigation`); the owner plays.
7. `kit world web <Name>` → `build/worlds/web/<Name>.html`: the whole world as ONE web page (three.js + the kit's
   own shaders: terrain layers, procedural materials, water, sky, height fog, sun shadows, HDR bloom, light shafts,
   grass, particles; orbit / fly / walk at R6 eye height; a parchment map; the graces and objectives as places).
   Show it to the owner — publish `<Name>.artifact.html` as an Artifact. It is the ART DIRECTION, not Studio's pixels.
   Examples (each its own game / place): `games/SampleRegion/` (an Elden Ring style region) and `games/SamplePeak/`
   (a northern hold in winter). Fast look: `kit world shots <Name>` (headless viewer, ~1 min) -> a contact sheet.
