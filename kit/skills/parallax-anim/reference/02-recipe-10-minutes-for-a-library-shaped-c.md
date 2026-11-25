<!-- reference for the parallax-anim route card; verbatim from the skill page (2026-10-16) -->

## Recipe (10 minutes for a library-shaped clip, 30 for a bespoke attack)
1. `lune run kit new anim <PascalName>` → `assets/animations/<Name>.json`: a sword slash with BEATS (anticipation →
   strike → follow-through → settle), a Hit event one frame after the impact, and a feel block.
2. Pose the keys (character space, degrees, applied at the joint — X = right, Y = up, -Z = forward; positive X
   lifts things forward/up):
   - `"Right Arm": [90, 0, 0]` forward · `[0, 0, 90]` out to the right · `[150, 0, 30]` overhead wind-up
   - `"UpperTorso": [0, 30, 0]` twists the UPPER body left (the waist). `"Torso"` is the ROOT joint: it turns the
     legs with it on both rigs — planted feet sweep sideways. Use UpperTorso for a twist.
   - `"Head": [20, 0, 0]` looks up · `"Right Leg": [45, 0, 0]` kicks forward
   A joint keeps its last value until a later key changes it. `{ "rot": [...], "pos": [...] }` adds a stud offset.
   A key's `ease`/`dir` shape the motion FROM that key to the next: Linear Constant Cubic Elastic Bounce; In (slow
   start) Out (fast start) InOut — the engine's words mean the same (measured 2026-10-10).
3. `lune run kit anim <Name>` → the clip `build/animations/<Name>.clip.json`, `src/animations/<Name>.model.json` (R6)
   and `<Name>_R15.model.json` (ReplicatedStorage.KitAnimations), the STRIP `build/animations/<Name>.png` + `.gif`,
   the MOTION METRICS `<Name>.metrics.json`, the place built and checked.
4. LOOK at the strip: columns = keys and events; rows = FRONT (its right arm on your left), SIDE (faces right),
   THREE-QUARTER; onion skins of the previous column, the hands' and feet's arcs over the whole clip, the timeline
   with beats and events (`<Name>.r6.png` / `.gif` = the R6 fold, which reads differently). Do the arcs read? Is the
   anticipation longer than the strike? Does the Hit sit right after the fastest frame? The strip is the kit's
   MEASUREMENT drawing (flat boxes); to see the clip as the game shows it: `lune run kit anim look <Name>
   [--rig R6]` bundles `build/animations/<Name>.look.luau` — run it through the Studio MCP (`execute_luau`, Edit
   mode) and a fresh humanoid loops the clip on its own lit pad far from the place's content
   (`Workspace._kit_anim_look`: select it and press F); `kit anim look --stop` bundles the remover. Blender:
   `kit anim blend <Name> --preview` writes `build/animations/<Name>.blend` (the clip keyed frame by frame on the
   kit rig) to scrub in Blender without changing the source.
5. READ the motion line: `RightHand peaks 60 studs/s at 0.37 s; Hit +1.3 frames vs the peak; feet planted; 0 pop(s)`.
   The gates fail a Hit more than 1 frame before / 3 after the fastest motion, a planted foot sliding > 0.1 studs in a
   frame, a one-frame snap, a loop whose last frame differs from its first, a part under the ground.
6. PROVE it in the engine: `lune run kit anim play <Name>` bundles `build/animations/<Name>.play.luau`; run it through
   the Studio MCP (`execute_luau`, `datamodel_type="Edit"` — no Play mode: the Animator is stepped frame by frame on a
   fresh humanoid, then destroyed); save the returned JSON; `lune run kit anim record <Name> <file>` compares every
   joint per frame with the clip (bar: 2 degrees, 0.05 studs, markers within 1 frame).
7. Play it in a game: `local Anim = require(ReplicatedStorage.kit.Anim)`; `local track = Anim.play(humanoid, "Slash")`;
   `track:GetMarkerReachedSignal("Hit"):Connect(...)` → the server validates, then deals damage. In Studio this works
   on the fly; live games upload with `lune run kit upload` (both rig versions).
