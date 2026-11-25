---
name: parallax-anim
description: Make Roblox R6 character animations (attacks, abilities, emotes, idles, hit reactions) that are MEASURED, not guessed — from a MOVE DOSSIER of the real move, authored from scratch by craft (director beat script -> gesture specs -> a pose prior -> the spring engine, dense 60 fps curves) and CALIBRATED by the loved native R6 catalog's statistics, gated on motion (Hit vs the fastest frame, planted feet, pops, seams, readability, statues), shown to the owner as pick sheets from the player's camera on their own rig, and proven in Studio frame by frame before upload. Use for any animation task.
---

# parallax-anim — the route card (the detail is in `reference/`; the record is in `kit/knowledge/vault/anim/`)

Start: `lune run kit status --dept anim` (the rulings, the golden set, the graveyard), then `kit help --stage
anim:<stage>`. Read `assets/rigs/R6_IK.md` before touching the rig: drive its CONTROLLERS (Body, Head.001,
Arm.R/L, FKLeg.R/L, Main Controller); never `obj.copy()` the armature; evaluate twice per frame (driver cycle).

## The clock and the route (the owner, 2026-11-10: "Yes, same budgets" - card b6m2)
- **The clock**: a piece gets 3D's budgets - 10 minutes simple, 30 complex, 60 hero (its spec's `"tier"`, a UI
  screen's `"quality"`; a clip's dossier is complex unless it says; hero only with `kit approve`). `kit anim <Clip>` / `kit anim bake <Clip>` start its dossier's; `kit anim` (every clip) starts any dossier new or changed since the last such build.
  A change is a change to what the piece is made of (its spec, the assets it names, a dossier's clip sources) -
  never a look's own output. Past the budget NO CHANGE builds (the piece as it was may still be played, looked
  at, rebuilt): show the owner what there is and its open cards; only his words reopen it: `kit clock anim
  <name> --extend <minutes> "<his words>"` or `--restart "<his words>"`.
- **The route**: its dossier's build block: the builder (strike, fp_weapon, locomotion ...) and its source kinds (.move, .pose, .gait, .import, a script); a clip is taken to the dossier that builds it. A piece made a NEW way (a way gained, not one dropped) refuses its build until
  `kit answer anim <name> --reroute` and every lesson is answered again for the new route (a copied answer
  does not count).

## LOOK at the move, large, beside its reference (the studio route's A0, 2026-11-12)
A pose was judged from 360 x 450 views framed on a sphere round the clip (the body a third of the picture, the blade out
of it, a flash ball on the tip at the Hit) and nobody saw the move's reference beside it. Now:
- **`kit anim sheet <Name>`** (about 17 s) -> `build/animations/<Name>.sheet/`:
  - `pose_sheet.png`: every KEY POSE (a row) on the owner's rig from the player's camera, the side and above, each pane
    768 px high and framed on that pose (a view's pane is as wide as its widest pose). Drawn on the renders from the
    kit's own FK: the blade tip's path through the keys (a numbered dot per key), the centre of mass dropped to the
    floor, the feet's support (green = the weight over it, orange = outside it). Beside each row: the dossier's
    REFERENCE FRAME of that pose's phase, or the gap SAID (why, the dossier's own words for the phase, how to add one).
  - `keys/`: the same panes two at a time. THESE are opened at full size, every one; `pose_sheet.png` is the owner's.
  - `strip_player.png` / `strip_side.png` (+ `strips/`): 12 frames a second, 512 px high, ONE camera, the hands',
    feet's and blade tip's paths with a dot on every strip frame (wide gaps = fast).
  - `look.json`: what every file shows. The key poses: the move's authored keys; a move with none (a procedural
    candidate carries its Hit only): its marks + the moments it nearly stops.
- **A reference frame** is the real move's own picture, in its dossier: `reference_frames: [{phase, video + t (seconds
  into the clip) | image (a still), game_t, note, source, view (player | side | top | front: which of our views it was
  filmed like), crop [x0, y0, x1, y1], flip}]`. Footage is private (`_artifacts/footage/<move>/`, never committed; the
  owner's yes before every download). A clip not timed like its dossier (a candidate) gets its phases counted in order
  round the Hit, and the sheet says so.
- **Every build ends with `LOOK: <folder> ...`**: `kit anim <Name>` renders each NAMED move's sheet by itself (the
  first 4 whose clip, move or dossier changed since their sheet; `--no-look` skips; a sheet that fails never fails the
  build) and names it in its last lines; a build of every clip renders nothing and names the sheets gone stale; `kit
  anim candidates` / `picks` / `look` / `bake` end with theirs. One candidate: `kit anim sheet <Name> --clip
  build/candidates/<Name>/round_K/<id>.clip.json`.
- Look BEFORE any gate number: does each pose read as its phase's reference, is the weight where the move needs it, do
  the feet do anything, does the path run clean through the keys. A fault of the move is a board card with the page
  that shows it; a sheet is never a verdict.

## A STRING of attacks starts with its DESIGN PAGE (the studio route's A1, 2026-11-13)
"They are cousins" is what a set looks like when every move is designed alone. A set is designed as ONE page first:
- **`kit anim design <Set> --new --attacks <n> [--weapon <word>]`** -> `assets/animations/designs/<Set>.design.json`:
  for each attack its `cut` as the PLAYER sees it (down, down_left, left, up_left, up, up_right, right, down_right,
  thrust), its `height` (high / mid / low), what the `body` does (plant, step_in, step_back, side_step, spin, hop,
  lunge, drop), its `intent` (calm / proper / aggressive), its `frames` at 60 a second (windup = the start to the
  Hit, active, recovery), the pose it `ends` in (words), and what may come `next`; and for the set, `links`: "pose"
  (every attack ends in the pose the next one starts in) or "blend" (the game blends from one to the next). Every
  TODO must go.
  A set of moves that exist: `--from <a.move.json>,<b.move.json>,...` measures what the keys say.
- **`kit anim design <Set>`** checks it and draws `build/animations/<Set>.design.png` (a row an attack: the cut on a
  wheel - red = designed, blue = what its keys measure - the frame budget, three silhouettes; the string's rhythm as
  one bar; every problem and note on top). LOOK at it, then show him.
- **What fails, each named with its attack**: the design not whole; COUSINS BY DESIGN (two attacks with one cut,
  height and body); and, once an attack names its `move` file (its keys; generated in memory, nothing is built):
  keys that cut another way than designed (more than 45 degrees off; a cut that runs mostly in depth is held only
  against its OPPOSITE - an "up" whose keys chop down fails), a wind-up or a length that is not the designed frames,
  and COUSINS BY MEASURE - two attacks whose blades run under 2.8 studs apart on average. Measured: the closest two
  attacks inside a set he loved run 6.1 studs apart, and no two distinct numbered attacks of a set built here run
  closer than 4.2; one cut made again runs at most 1.6 from itself (every key's yaw, pitch and roll turned up to 25
  degrees, the grip moved half a stud on each axis; 1.3 on the other weapon). The path is read against the body,
  so the same cut with a step added is the same cut. NOT cousins, and said as a note: the same cut designed at two
  heights whose blades measure a stud or more apart at the Hit. The angle between two cuts does not tell cousins
  (two loved attacks cut within 14 degrees of each other, 8.9 studs apart).
- **The string's links**: in a set linked by "pose", an attack that ends more than 6 degrees from where the next
  starts BREAKS the string and fails, named with the joint ("attack 1 (Katana1Kesa) ends 145 deg from where
  Katana3Makko starts (Right Arm)"). The link is read as the game plays it (with the move's steps, at 60 frames a
  second) and the blade's own direction counts. Measured: the two strings he loved link within 0.4 to 4.9 degrees;
  the strings here that the game blends end 86 to 180 from the next start. In a set linked by "blend" the number is
  a note; a link with no keys yet is said as not measured. Which of the two a set is, is part of the design he
  approves.
- **His yes**: draw the page (`kit anim design <Set>`), show him THAT page, then `kit anim design <Set> --approve
  "<his words>" --by owner --id <the id on the page he saw>`. It is refused when no page was drawn, when the page
  is another design's, or when the design's problems changed since the page was drawn. It is to the design as it is
  (a design changed after it is stale) and to what that page printed: its problems are accepted exactly as they
  stood and said again, never failed again; a problem that appears or whose numbers move after it fails. A record
  without the page he saw is no yes.
- **The lock**: a move made after the rule that a design names is not made (`kit anim <Name>`, `kit anim candidates
  <Name>`) unless that design has his yes as it is now; so is a move a game's style (`anim_style.json` "sets") lists
  in a set that has no design page (the active game's style, or every game's when none is active). A design, record
  or style file that cannot be read frees nothing: it holds every move asked about. Then each move starts with its
  blocking (below). A strike or sword move that no
  design and no style set names is a move on its own: the blocking lock alone holds it.

## Two checks in every build's motion gates (his method lists, 2026-11-13)
Both run inside `kit anim` and `kit verify` on every built clip (`kit/anim/metrics.py`), with no command to remember:
- **The weapon in a hand at every frame** (`kit/anim/in_hand.py`; alone: `python kit/anim/in_hand.py <clip.json>`).
  In the game the weapon rides the right arm on its own joint, so a clip whose weapon path leaves the hand is
  exported with the weapon floating. At every frame the nearer hand must be within 0.1 studs of the weapon's line
  (hilt to tip: a hand along the blade in a half-sword block is holding it; a held weapon reads 0.00). Out of both
  hands is MEANT only when the clip's own events say so by their WHOLE name (a weapon's name may lead it:
  SwordToss, GunsOut): from Toss / Throw / Pass / Release / Drop / Sheathe / Holster / OnBack / Vanish to the Catch /
  Caught / Out / Draw / Appear that answers it (two tosses need two catches; another weapon's event closes
  nothing) or to the clip's end, and from the start to the last "back" event before anything leaves (a draw).
  Otherwise the clip FAILS: "the weapon is in NO hand for 5 frame(s) ... frames 10-14". A weapon track shorter than
  its clip fails too. The 8 clips that fail today are frozen in `assets/animations/blocks/_weapon_loose_before.json`
  (said, never failed; never add a name to it). Limits: a weapon slid along its own axis or flipped end for end
  still reads as held; one weapon track is read (not a second gun).
- **The hands PUT ONTO the weapon** (`kit/anim/grip_solve.py`). A clip from any route whose hand is off the weapon:
  `{"op": "grip", "hands": "two" | "right" | "left"}` in a derive recipe turns each named arm about its shoulder and
  slides it until the hand is on the hilt - the weapon stays where it is. A hand near the weapon goes to the nearest
  point of the hilt, a hand far from it to where the loved cuts hold (half the grip spacing either side of the grip
  point); `"at": {"right": studs, "left": studs}` says the places (a staff, a half-sworded blade). FAILS, named: no
  hands said, a weapon the arm cannot reach 2.5 studs out of its shoulder, a hand put through the body, an arm that
  would jump, a weapon track that is not the clip's length. The solved clip says its hands; the gate above holds it.
  Run it through `python kit/anim/derive.py` or alone (`python kit/anim/grip_solve.py <clip.json> --hands two`):
  `lune run kit anim derive` rebuilds its clip from body keys and would drop the weapon and the hands.
- **A path drawn for the blade** (`kit/anim/blade_path.py`). A move may state the points its blade tip passes
  through: `"blade_path": {"tol": 0.5, "points": [{"t": 0.30, "tip": [x, y, z]}, {"tip": [x, y, z]}]}` in the keys'
  own space (a point with a time is passed at that time, one without in order, one pass for one point). The
  finished clip's tip must come within `tol` studs of each (1 stud at most), or the clip FAILS naming the point
  ("MISSES 2 of the 10 point(s) ... point 5: 1.02 studs"); a point timed past the clip's end is a miss. A clip
  built from another clip (a feel pass, a re-arm, a warp) is held to its BASE move's path. Start from the clip's
  own path: `python kit/anim/blade_path.py draw <clip.json>`, move the points, put them in the move. A move that
  draws no path is held to nothing. Limits: the body's travel (a step, a dash) is not part of the path; ten points
  a tenth of a second apart do not catch a blade turned 30 degrees at one key.
- **A path drawn for a hand or a foot** (the same file). `"paths": {"RightFoot": {"tol": 0.5, "points": [{"t": 0.30,
  "at": [x, y, z]}, {"at": [x, y, z]}]}}` for RightHand, LeftHand, RightFoot, LeftFoot: the hand, or the sole's
  centre, in the CHARACTER's space with the clip's own travel carried (where the world sees a kick's foot), not the
  keys' space. Same rules and the same FAIL ("the right foot of X MISSES ..."); a name that is no hand or foot is a
  problem. Start from the clip's own: `python kit/anim/blade_path.py draw <clip.json> --of RightFoot`.

## Curve tools in a derive recipe (his method lists: Graph Editor editing, 2026-11-14)
A DRIVER (`kit/anim/drivers.py`, his method lists: driver / expression-driven animation) is a third op:
`{"op": "drive", "joint": "Head", "by": "Torso", "weight": 0.5, "delay": 0.05, "axis": [0, 1, 0]}` - the joint is
given `weight` times the turn the driver has made since the first frame (negative: the other way; followed all the
way round, no jump past 180 degrees), read `delay` seconds late, `axis`: only its turn about that axis. A part still
rides its parent (Head by Torso 0.5 = one and a half times the torso in the world). It REFUSES, leaving the clip as
it was: a hand taken more than 0.1 studs further off the weapon at ANY frame (so an arm or the torso of a sword
clip cannot be driven), a loop that would not close, any delay on a loop or on a stepped clip.

Two ops for `kit anim derive` (`kit/anim/curves.py`):
- `{"op": "filter", "hz": 8, "joints": ["Head"], "keep": [0.43]}` - a signal filter with no time shift: half of a
  shake at `hz` a second gets through, less of anything faster. The first and last frame, every Hit and every time
  in `keep` stay exactly where they were. For a track that shakes (a capture, a solver that chatters), never as a
  polish. It REFUSES, leaving the clip as it was: a stepped clip; a filter that takes a hand more than 0.1 studs
  off the weapon (the blade is never filtered, so on a sword clip the torso and the arms cannot be - the head and
  the legs can); a filter that takes more than a tenth of the motion (the strike's path, how far a joint gets from
  its first pose) unless the recipe says `"soften": true`.
- `{"op": "handles", "from": 0.20, "to": 0.40, "out": [0.2, 1.0], "in": [0.8, 0.0]}` - tangent handles on one
  stretch's timing: the motion between the two times is replayed along a bezier in time (`out` leaves the first
  pose, `in` arrives at the second; [0.33, 0.33] / [0.67, 0.67] is as it was). Both poses, the clip's length and the
  blade's length are kept. It REFUSES a stretch with a Hit inside it, and handles that make the strike's fastest
  frame more than twice as fast as it was (a hold, then a snap that pops).
These are tools a recipe may use; nothing forces them. What holds their result is the same as for any clip: the
motion gates, the weapon-in-hand check, and the poses you approved.

## A PROP's rig and its clips (his method lists: object animation, 2026-11-14)
- `python kit/anim/prop_rig.py make <prop.json> --out <rigs>/<name>.json`: a prop's rig from a few lines of data
  (axis-aligned boxes at rest; each part its `parent`, the `pivot` where the two touch, and a `hinge` or a `slide`
  with its axis and range - a hinge inside -180 to 180 degrees, -180 / 180 = spins freely) in the kit's own rig
  format. The kit's FK and Roblox's Motor6D rule agree on it (a clip frame is the joint's own transform).
- Any clip on a prop's rig is held to its joints inside the build's motion gates (`kit/anim/metrics.py`; alone:
  `python kit/anim/prop_rig.py clip <clip.json> --rig <rig.json>`): a hinged part turns only about its axis and
  inside its range, a sliding part moves only along its runner, a fixed part and the root do not move - "Lid turns
  to 140 deg; its hinge runs 0 to 110 at frame 30". A prop is not judged by a character's gates (feet, Hit).
- THE WHOLE WAY: `lune run kit anim prop <Prop>` reads `<anims>/props/<Prop>.prop.json` and every keyframe spec in
  `<anims>/props/<Prop>/` (the kit's own spec format, `"rig": "<Prop>"`, a key's pose each part's OWN turn and slide
  relative to its parent: `{"Lid": [90, 0, 0]}` degrees, or `{"rot", "pos"}`), compiles each with the kit's own
  compiler, holds the clip to the prop's joints, and only then keeps the KeyframeSequence model the game plays:
  `<animOut>/props/<Prop>/<Clip>.model.json` (models only; the rig, clips and the manifest of what was built and
  what was refused go to `build/animations/props/<Prop>/`). A spec whose clip breaks a joint leaves NO model, and
  what the last build of that prop left is removed first; two specs of one name are both refused.
- A PROP THE 3D LANE BUILT: `lune run kit anim prop <asset> --model` reads the rig from the built model's manifest
  (`build/models/<asset>.manifest.json`: every hinge and slide its build script names with a.joint), with the very
  joint frames `src/kit/Models.luau` spawns, so the clip plays on the model the game already has. Part names are
  the group names; a pose is said in the parent's space at rest (a wheel on a [0, 0, 1] axis: `{"wheel": [0, 0, 90]}`)
  and the compiler turns it into the joint's own turn (what `Models.pose` sets). `--tool`: the model is spawned by
  `Models.tool` (its root is named Handle). `--check`: are the clips the last build left still made on the joints
  the model has NOW (a part renamed, an axis turned, a range changed)? Run it after the model is rebuilt.
  Refused, named: a moving part hung on a part that does not move, two joints on one part, a range that does not
  include 0, a hinge past 180 degrees either way.
- NOT there yet (card r66z): the game's runtime has no prop player (an AnimationController on the spawned model
  and a call that plays the clip), no prop's clip has been played in Studio, no gate runs `--check` by itself, and
  a prop typed as a prop FILE has no Roblox model (build it in the 3D lane with a.joint and use `--model`).

## Matching and runtime rules (his method lists, 2026-11-14) - pose / distance matching have their way in
- THE WAY IN (pose and distance matching): a move or a keyframe spec says
  `"match": {"pose": true, "distance": true | "<Event>"}`. Every `kit anim` build then bakes the tables into the
  game's animation data (`Meta.<Clip>.match`: the frames before its first Hit; a pose table 30 rows a second at most, a distance table one number a frame), and a
  clip that asks for a table it cannot give FAILS the build, named. In the game:
  `Anim.play(owner, name, fade, weight, speed, { enter = "pose" })` starts the clip at the frame nearest the pose
  the character is in; `{ distance = studs }` at the frame that far from its stop (a clip that travels then moves
  the body only what is left of its travel). Studio-unproven: the pose read off a live character, the track's
  time set before it has loaded, what the server sees of a player's pose.
- CLEAN-UP in a derive recipe (`kit/anim/cleanup.py`): `{"op": "plant", "max_shift": 1.5, "travel": false}` -
  planted feet that skate past the build's bar (0.1 studs a frame) are held still by moving the body over them
  (the root track); a clip that passes is left untouched. Refused: a loop, a stepped clip, a clip with no root
  track unless `"travel": true` (the game would then move the character through the move), travel taken for a
  skate, two feet that only drift apart.
- A prop built on a 3D-lane model: every `kit anim` build and its verify gate now run the props' `--check` by
  themselves (clips made on joints the model no longer has are an error).
- THE WAY IN of three runtime rules (2026-11-14; instance code, Studio-unproven):
  - GET-UP BLEND: `AnimRagdoll.knock(character, push, seconds, { blend = 0.35, getUp = { back = "<clip>",
    front = "<clip>" } })` - `Moves` passes a move's `onHit.getUp` / `onHit.getUpBlend`. A joint's pose does not
    travel between machines, so what a player SEES is blended on that player's client: the kit's client script
    calls `AnimRagdoll.watch(character)` for every player's character (call it yourself for an NPC).
  - FOOT PLACEMENT: `local stop = Anim.feet(character)` - on each CLIENT, for every character it shows (on the
    server it is seen by nobody). In the air it eases back to the clip's own.
  - CROWDS: `AnimCrowd.track(character)`; `Anim.feet` asks `AnimCrowd.due(character)` and places a far character
    every 2nd or 4th frame, or not at all. Roblox throttles its own animation by distance already: this is for
    what the kit adds after it.
  - MOTION MATCHING: a MOTION SET is a file `assets/animations/motion/<Set>.motion.json` =
    `{"clips": ["<Clip>", ...], "rest": "<a looping clip of the set>"}`. Every full `kit anim` build bakes its
    database into the game (`KitAnimations.Motion`, 30 rows a second) and FAILS, named, on a set that names a clip
    the build did not make, has no looping rest, or holds a 60-a-second loop of an even number of frames. In the
    game (on the client that shows the character, R6): `local stop = Anim.motion(humanoid, "<Set>")` looks a few
    times a second and cross-fades to another clip of the set when its motion fits the body better; a clip is
    never scrubbed within itself, a clip that does not loop plays out and the body goes to the rest.
    NOT built: steering by where the player wants to go.
  - SECONDARY MOTION: accessories sway on a spring (`src/kit/AnimSecondary`, the rule `AnimLayers.sway`). Off unless
    the game asks: set the attribute `KitSecondary = true` on `ReplicatedStorage.kit` (optional
    `KitSecondaryStiffness` / `Damping` / `Gain` / `Max`); the kit's client script then attaches it to every
    player's character. Which way an accessory tips has not been seen.
- AN UPPER-BODY VERSION of a move (animation masking): a move or a keyframe spec says `"upper": true`. Every build
  then ALSO makes `<Name>Upper` - the same R6 clip with its legs left out - and names it in the move's data
  (`Meta.<Name>.upper`); the game (`src/kit/Moves`, the rule `MovesRules.clipFor`) plays that version instead of
  the move while an R6 character is being moved, so the walk keeps the legs under the attack. The build FAILS,
  named, on a move that asks and cannot have one: it travels, it is an upper-body move already, it keys no leg,
  or its TORSO turns more than 15 degrees or moves more than 0.1 studs (R6 has no waist: the walking legs hang
  off the torso and would be carried with it - a version without the body's turn is another look, the owner's
  call). The version is the move's own gated motion minus its legs: it gets no gates, strip or look of its own.
- WHAT EACH FOOT IS DOING (`kit/anim/foot_modes.py`; alone: `python kit/anim/foot_modes.py <clip.json>`): every
  foot's clip in stretches - airborne, plant, pivot, slide. A slide the move MEANS is SAID, never passed by raising
  `gate.foot_slide` (that switches the feet off for the whole clip): `"slides": [{"foot": "Right Leg" | "Left Leg" |
  "both", "from": s, "to": s, "kind": "skid" | "drag" | "scrape" | "roll"}]` in the move, the spec or the clip.
  Inside it that foot is not judged; outside it is, at the ordinary bar. A said slide that is not there FAILS.
- NOTHING PASSES THROUGH THE BODY (`kit/anim/collide.py`, a gate of every build, 2026-11-15): the weapon, the hands
  and the feet are read against the body's blocks, SWEPT between frames; over a bar the build FAILS with the part and
  the frame. A contact that is MEANT is said in the move or the spec: `"contact": [{"a": "weapon" | "<part>",
  "b": "<part>", "from": s, "to": s}]`. Two hands on one hilt are the grip, not a fault. REPAIR
  (`kit/anim/collide_repair.py`): `{"op": "clear"}` in a derive recipe moves a hand (the arm turned and slid), a foot
  (the leg turned) or a ONE-handed blade (turned about the hand on it) out by the least that does it, inside bounds
  (30 degrees, 0.45 studs, 25 degrees), eased over six frames - or the recipe FAILS saying why: an arm that holds
  the weapon and a two-handed blade are never moved (change the move's keys), nor a fault past its bounds.
- WHERE A STRIKE MEETS ITS TARGET (`kit/anim/contact.py`, a gate of every build): every contact the geometry sees
  (the striker's line arriving at a target's chest 3 studs ahead, or at `"target": [x, y, z]`), each with a
  confidence from three kinds of evidence (geometry, a speed peak, an authored event). A Hit the BUILD placed at a
  speed peak that the geometry puts more than 3 frames elsewhere FAILS: author the Hit. An authored Hit is only said.
- ONE FINISH FOR EVERY ROUTE (`kit/anim/finish.py`): any source (move, keyframe spec, gait, import, pose, bake) may
  say `"finish": {"filter": {...}, "velocity": {"max_deg_s": n}, "handles": [...], "overshoot": {"max_deg": n}}`; the
  build applies it at one place, to the R6 clip, always in that order, and REFUSES a finish that changes the clip's
  length, an event, or the pose at an end or a Hit. A clip that asks and is not stamped fails the gates.
- FRAMES A CAPTURE DID NOT SEE (`{"op": "gaps"}` in a derive recipe, `kit/anim/cleanup.py`): frames under the clip's
  own `"confidence"` and dropped frames (repeats with motion either side) are re-made between their neighbours and
  LISTED for review; a gap over an event, an end, or a foot's landing or lift is refused - a contact is not invented.
- A CLIP AS A ROBLOX CURVE ANIMATION (`src/kit/AnimCurve`, in Studio: `AnimCurve.fromSequence(sequence)`): the same
  motion with the keys a straight stretch does not need left out (within 0.25 degrees / 0.005 studs). KNOW THIS
  FIRST: Roblox plays a curve animation at 30 samples a second (measured 2026-11-15) - a 60-a-second kit clip loses
  its odd frames (5.2 degrees on a fast cut's arm); the report says the loss and the builder warns. The kit's own
  clips stay KeyframeSequences (every frame plays). A curve animation is for a clip made at 30 a second.
- ACCESSORY SWAY BY KIND (`KitSecondary = true` on ReplicatedStorage.kit, as before): hair, a cape, a sheath and a
  hat now each move on their own spring inside their own limits (small toward the body: the stand-in for
  collision); a face piece and clothing do not sway; far from the camera it is stepped less, then not at all.
  An accessory must be worn by its ATTACHMENTS (the engine welds one without them onto the head).
- WHAT A CLIP COSTS (`python kit/anim/budget.py <Name>.clip.json`, or `table build/animations`): its exported
  bytes, the keys a curve within 0.25 degrees / 0.005 studs would keep, and what the engine's 30-a-second curve
  playback would lose - a curve is free only where that loss is inside the tolerance (a clip made at 30 a second);
  otherwise the clip stays a KeyframeSequence. Named, never failed.
- WHAT THE CATALOGUE COVERS (`python kit/anim/catalog_coverage.py ask "<the move in words>"`, before a move is
  built): familiar (10 or more loved, game-usable clips have everything the words ask), thin (1 to 9), or
  UNSUPPORTED with what is missing - then the move's numbers must come from its own dossier, not the catalogue's.
  `report` shows every axis and the empty weapon-by-direction cells; `verdicts` the owner's verdicts by standing.
- WHAT EACH PHASE RESTS ON (a new dossier is schema 3): every phase that moves says
  `"evidence": {"basis": "measured" | "inferred" | "told", "from": "<source id | what it was inferred from | owner>",
  "note": "<the owner's words, when told>"}`. `measured` needs `real_s` in numbers and where they were measured
  (`real_s_from`, or a source of the phase's own with `measured` numbers). A strike's contact or wind-up on
  inference is refused unless the phase says `"accept": "<why it stands>"`. Read any dossier:
  `python kit/anim/dossier_evidence.py <move>`; all of them: `... table`.
- A PAIRED MOVE THAT CAN BE BROKEN OFF (`Cutscene.play(name, anchor, cast, { breaks = { commit = 0.8 }, onBreak =
  function(verdict, exits) ... end, clock = function() return workspace:GetServerTimeNow() - startedAt end })`):
  a body gone, dead, stunned from outside (`KitStunned` on its model) or moved off the plan ends the scene for
  everyone; `verdict.reason` / `verdict.who` say why, `exits[role]` what each body does ("release", "stagger",
  "fall", "none"). After `commit` only gone and dead end it. Unsaid, nothing breaks a scene. Rule: `AnimPaired`.
- ONE FRAME CONVENTION (`python kit/anim/frame_contract.py`): +X is the character's right, +Y up, -Z ahead, studs,
  right-handed turns at the joint (a positive turn about +X lifts a hanging arm ahead; about +Y turns the face
  left). A calibration motion with hand-written places holds every route to it (Python, the Luau compile, the
  import back, the mirror, the fold; the engine was read in Studio). A NEW route (an importer, an exporter) must
  reproduce it: `python kit/anim/frame_contract.py check <points.json>` reads places off any route.
- WHAT A RIG CHANGE LOST (`python kit/anim/fold_loss.py <Name>.clip.json <Name>.r6.clip.json`, `table <folder>`):
  an R6 fold against its R15 source at the hands, feet and pelvis - what no R6 can keep (a bent elbow) is recorded;
  a striking limb more than 0.6 studs the wrong way at the Hit fails the fold's build (the fold was changed
  afterwards, or is broken: fold it again). The kit's fold already aims each arm at the source's wrist.
- TIMING THAT FOLLOWS THE DISTANCE: a move with a root travel may say `"warp": {"from": .., "to": .., "pace": true}`.
  The game then plays its standing part (the wind-up) and its travelling part at rates that follow how far the warp
  reaches - far: a shorter wind-up, a longer run; near: the other way - and the time to the window's end (the Hit)
  does not change. Bounded (travel x1.33, wind-up x1.5); a move that travels from its first frame has nothing to pace.
- THE STRIKE FROM THE PLAYER'S CAMERA (`python kit/anim/camera_read.py <clip.json>`, or `table build/animations`):
  how much of the strike is seen to move from the game camera behind the body and 45 degrees to either side (hidden
  behind the body, or travelling along the camera's line). Every strike's metrics carry it as `camera`. A READING to
  point your eye, never a verdict: it does not tell the owner's loved cuts from the rejected ones.
- THE MOMENTS BETWEEN THE MOVEMENT LOOPS (`Anim.locomotion(character, set)`): beside idle / walk / run the set may
  name `start`, `stop`, `pivot`, `turnLeft`, `turnRight` - each played once over the blend when the body starts,
  halts, reverses or turns where it stands (read off its velocity: a player and a `MoveTo` body alike), entered by
  pose when the clip says `"match": {"pose": true}`. The library has NO such clip yet: they are moves to make.
- ATTENTION (`Anim.lookAt(character, target, { body = 0.3 })`, `Anim.attention(character)`): the head turns to a
  target on a spring; with `body` the torso takes that share (20 degrees at most; the legs stay where they stand).
  A target behind is let go (no head thrown from shoulder to shoulder); the look yields while a move has committed,
  in a ragdoll, on a seat. `attention` holds several targets by priority: `attend:set("threat", part, 5)`.
- ONE EFFECT FOR ONE MARKER (`Anim.marker(track, "Swing", events):Connect(fn)`, the rule in `src/kit/AnimMarks`):
  hang an effect on a clip's marker through this, not on the engine's signal. The engine fires a marker AGAIN when
  the clip's time is wound back and NEVER for one the time jumps over (a clip entered late); taken through the
  record it runs once a pass, never after a stop, and gets the marker's own time and how late the handler is.
  `Anim.skippedMarkers(clip, at)` names what a late entry jumped over. Damage is never hung on a marker: `Moves`.
- A ROOT TRAVEL THAT MEETS THE WORLD (`src/kit/AnimWarp`, called by `Anim` for every move with a root track): the
  warp window's travel is swept and cut short of a wall, every frame's step stops short of what it meets, the
  target is followed until the move commits (half-way through its window), and a body something else moved on
  purpose keeps its new place. Written, never seen to move.
- STEERED MOTION SETS (`Anim.motion(owner, set, { steer = true })`): every row of a set carries where its clip is
  going (a gait's speed and direction, a root's next 0.3 s, or the set file's `"travel"`); the search counts the
  miss against where the player pushes. A move in flight is not steered; steering never starts a move.
- FEET WITH CONTACT STATE (`Anim.feet`, the default): each foot is planted, swinging or unsupported; only planted
  feet carry the pelvis; a sole stands on the highest ground under it; a planted foot meets a support that rises.
  `{ contact = false }` keeps the first rule.
- THE CLIENT'S LAYERS HAVE A LIFECYCLE (`src/kit/AnimLife`, `src/kit/client/AnimRoot.client.luau`): feet
  (`KitFeet = true` on ReplicatedStorage.kit), a motion set (`KitMotionSet = "<Set>"` on a character), secondary
  motion and the get-up watch are one of a kind per character, stopped at a respawn or a leave, stood down while a
  ragdoll has the body. Written, never seen to move: a Studio session proves them.
- THE WHOLE RULE of what the runtime already ran is spec'd (`kit/test/spec/animwhole.spec.luau`,
  `animsecondary.spec.luau`): the attack state machine's cancel window at its edges, busy, the combo's gap, the
  parry's lockout (`MovesRules.parryAllowed`); the locomotion blend's own back / strafe clips, partial sets and
  the air (`AnimBlend.oneShot` / `falling` / `airborne`); the motion warp inside, after and before its window.
- `lune run kit anim match pose|distance|motion <clip.json>... [--to <Event>] --out <table.json>`
  (`kit/anim/match_tables.py`) bakes the tables the game matches against; `src/kit/AnimMatch.luau` answers from
  them (pure maths; the tests hold the game's answers to the build's):
  - POSE MATCHING `AnimMatch.poseFrame(table, pose)`: the frame to ENTER a clip at, nearest the pose the character
    is in - only before its first Hit (a loop anywhere; no Hit: its first half).
  - DISTANCE MATCHING `AnimMatch.distanceFrame(table, studs)`: the frame at which that distance is still to travel
    to the stop (or to `--to` an event). Refused: a clip that does not travel 0.5 studs, a body that steps back.
  - MOTION MATCHING `AnimMatch.motionNext(db, pose, vel, current)`: from the pose now and how each joint turned
    since the frame before (`AnimMatch.velocity`), the frame of several clips to play NEXT; it stays on its clip
    unless another row fits better by `stay` (0.05, measured on three loved cuts only: a number to tune in a game).
- `src/kit/AnimRules.luau` (pure maths, spec `kit/test/spec/animrules.spec.luau`):
  - FOOT PLACEMENT `AnimRules.feet(left, right)`: the ground's height under each foot -> the pelvis's drop and
    each leg's slide in its hip (R6: a leg slides, it does not bend), and how far short a foot is past the limits.
  - GET-UP FROM A RAGDOLL `getUpSide`, `getUpOffset` (once), `getUpFrom` (each frame): a joint from where the
    ragdoll left it to the get-up clip's pose, no jump, no overshoot.
  - CROWDS `AnimRules.crowd(distances)` + `due(every, frame, rank)`: who is animated every frame, every 2nd,
    every 4th or not at all, nearest first inside two budgets, a frame's work spread evenly.
- What waits on Studio: reading the pose and the ground off a live character, writing the answers after the
  Animator, capturing a ragdoll's pose, and seeing any of it move.

## The TIMING CHART (his method lists, 2026-11-13: it was a file no command ran)
- **On every sheet**: `timing.png` in the sheet's folder - the striker's speed and its spacing frame by frame (wide
  bars = fast, dense = easing), the sheet's key poses and the Hit marked - and its reading in words on the `LOOK:`
  line: "the blade tip gathers 5 frame(s), cuts in 15 (fastest at frame 26, 169.6 studs/s) and is quiet for 20
  after; the Hit is at frame 26, on the fastest frame; widest spacing 1.84x the cut's average; frames between keys
  11 | 8 | 6 | 7 | 19". A sheet made before the chart is stale. A clip with no blade charts its fastest hand or foot;
  a clip with several Hits is read at each one; a STEPPED clip is read on its smooth motion (read raw, every cut is
  one frame long and evenly spaced); a BLOCKING's chart says "held poses: no spacing to read" and counts only the
  frames between its poses.
- **Alone, in a second**: `kit anim timing <Name> [--clip <clip.json>] [--move <move.json> | --no-move]` ->
  `build/animations/<Name>.timing.png` (a clip named by `--clip` is charted alone unless its move is named too).
  Charted against a move that is not its own - the file names another clip, has no two timed keys, or its last key
  is not the clip's last frame - it is NOT drawn and says so.
- Read it for: the frames between the keys (the rhythm), where the spacing is wide and where dense, the Hit against
  the fastest frame. The numbers are CAPTIONS, never a gate: measured on the kit's fixtures (7 cuts he loved, 3 he
  rejected) the gather / cut / quiet counts and the spacing do not tell the two apart. Where the Hit sits in the clip
  does on those ten (loved 0.48-0.55 of the length, rejected 0.34, 0.37, 0.71) - but the loved seven come from two
  sets built one way; a rule from that would be a guess.

## BLOCKING the owner answers from a picture (the studio route's A2, 2026-11-13)
Every sword move he loved had its key poses designed and corrected BEFORE the in-betweens; every one rejected on
11-04 came from candidates whose poses nobody showed him first. The only blocking step was work for him (open the
.blend, move the rig). Now, before any motion is made:
- **`kit anim block <Move> --sheet`** (about 20 s; builds nothing, starts no clock) -> `build/animations/<Move>.blocking/`:
  the move's key poses HELD at its own timing (`blocking.clip.json`, a stepped clip), as the pose sheet (every POSE
  large from the three views, how long it is held, the reference column) + `blocking.gif` (pose, hold, pose in real
  time from the player's camera). The poses come from the move's keys (`assets/animations/<Move>.move.json`, or
  `--move <file>`), a procedural weapon dossier's gesture at neutral efforts (`--proc <dossier>`: its beats), or a
  clip (`--clip`). A blocking shows EVERY pose (a sheet thins to ten; a move keyed densely names its poses in
  `block_keys`). Look at every keys/ page yourself first, then show him the sheet and the gif.
- **His words on a pose**: `kit anim block <Move> --note <pose> "<his words>"`. The note is kept with the pose as he
  saw it (`assets/animations/blocks/<Move>.blocking.json`, tracked) and FOLLOWS that pose by its authored key (a key
  added or dropped before it renumbers the note, never moves it to another pose). The next `--sheet` prints it on
  that pose's row: ANSWERED (what changed: "Right Arm turned 16.6 deg") only when that pose's OWN key was edited or
  retimed; NOT ANSWERED while it is as he saw it - and also, with what changed said, when the pose only changed with
  its neighbours or its hold (a generator carries one key's change on: turning the loved kesa's pose 3 by 15 degrees
  moves pose 5 by 8.7), when the source is a clip (no keys to tell a correction from a ripple), or when the pose is
  gone (said at the top of the sheet). Those are closed by his yes, never by the kit.
- **His yes**: `kit anim block <Move> --approve "<his words>" --by owner --id <the id in the first line of the sheet
  he saw>` (only his, only when given). It is a yes to THAT blocking: its poses are stored with it, and any later
  change (a pose turned, retimed, added, dropped) makes it STALE and names the pose and the limb. A note after his yes
  reopens the blocking. A blocking older than its move (the move file changed since `--sheet`) takes no note and no
  yes and tells no state: make the sheet again and show him that one.
- `kit anim block <Move> --state [--need approved]` says where it stands (waiting / notes open / answered /
  approved / stale).
- **THE LOCK - poses first, motion after** (his order of 2026-11-13: every method "enforced in the terms of being
  used"; the studio route's A2). A strike, sword or kick move made AFTER the rule is NOT MADE, at any build, unless
  his yes stands for its key poses as they are now:
  - `kit anim <Name>` refuses a strike move (`<Name>.move.json`) and a dossier pick (`<Name>.dossier.json`) whose
    dossier is built on a strike move file, on a sword gesture, or keyed as a kick or unarmed strike (`build.keys`:
    `kit anim block <Name> --sheet --proc <dossier>` shows those keys held - the roundhouse's eleven in 0.3 s);
    `kit anim candidates <Name>` refuses the same moves' candidates (candidates ARE motion; with `--blade <gesture>`
    show that gesture: `kit anim block <Name> --sheet --proc <dossier> --blade <gesture>`). The refusal names the
    command that shows him.
  - Made before the rule = named in `assets/animations/blocks/_before_blocking.json` (129 moves, frozen 2026-11-13
    by `python kit/anim/blocking.py freeze`; a project with no list has none). Those are never asked. NEVER add a
    name to that list to get a move built.
  - His yes counts only as recorded by `--approve ... --by owner --id <id>`: the record must say it was his, hold
    the poses he saw and carry their id. A yes to poses that changed since (a key turned, retimed, added, dropped)
    is stale and holds the move again - at its first build and at every later one.
  - What holds what: a strike move is held to its keys' poses by the lock and its built clip to them by `--check`.
    A sword or kick pick is held to its GESTURE's / its dossier keys' poses by the lock; its built clip is held by
    `--check` only once he also said yes to the pick's own poses (`--sheet --clip <the pick's clip>`): a gesture yes alone is not a gate on
    the clip (a pick's efforts re-pose the gesture by design).
  - A HAND-POSED file (`<Name>.pose.json`, 2026-11-14) is locked too: `kit anim block <Name> --sheet` has the
    owner's rig pose its keys (about a second in Blender, into the blocking's folder: no build, no clock) and holds
    them as the sheet; his yes is to the file AS IT WAS (its content, not its bytes): any change to it since makes
    the yes stale. The 213 posed files of 11-14 are frozen in `blocks/_before_blocking_posed.json` (that list
    excuses posed files only). Not asked: a posed file the owner made his own `.blend` of (`kit anim edit`).
    `kit anim tune` rewrites a posed file per candidate: a posed move made after the rule cannot be tuned before
    his yes.
  - NOT locked: a hit reaction (simulated from an impulse: it has no key poses - the lock says so); and, never
    read by the lock (card r66z): a `.blend` source and its bake, a keyframe spec, a gait, an import.
- The gif shows EVERY pose for as long as it is held (a pose held one frame gets the gif's shortest frame, 20 ms).
- **The finished clip is HELD to the poses he approved** (A4): `kit anim block <Move> --check [--clip <clip.json>]`, and
  every build (`kit anim <Move>`) and `kit verify` run it on a move that has his yes. Each approved pose is looked for
  in the clip AT ITS OWN MOMENT (0.05 s either side, between frames too): his yes was to the rhythm as well, so a clip
  retimed, slowed, lengthened or cut short is no longer it. A pose the clip never comes within 10 degrees / 0.25 studs
  of - or whose blade points 10 degrees off, or whose tip is 1.25 studs away - FAILS, named with what is off: "pose 3:
  Left Leg is 15.1 deg from the pose he approved". Measured: the loved kesa rebuilt from its approved keys 0.0 deg; one
  key turned 15 deg named; 122 of the 124 strike clips built here are 0.0 deg from their own move's blocking (the two
  others were not built from that move file). A stepped build is read on its smooth motion (steps are presentation).
  A move with no approved blocking is held to nothing. The fix is the pass that moved the pose, or a new blocking
  shown to him - never the tolerance.
- **A procedural pick**: his yes to a GESTURE's neutral blocking (`--proc`) is a yes to the design and is NOT a gate
  (a pick's efforts re-pose the gesture by design: `--check` says how the clip differs, the build passes). What a
  build is held to is the pick's own poses: `kit anim block <Name> --sheet --clip <the pick's clip>`, his yes on that.

## The owner's rulings, in order (later ones win; every one has a date)
1. 2026-10-11: R6 ONLY on the owner's IK rig; finished native Roblox R6 animations are the quality bar ("WOW THOSE
   ARE AMAZING"); mocap / other engines folded to R6 "all bad"; looks filmed from BEHIND were the cause of a day of rejections.
2. 2026-10-12: sets authored from 8 key poses "genuinely horrible, 3/10" (judges said 4.2-5.0 — the judge loop is
   refuted); "INVENT the moveset BY YOU, USE the catalog as DATA"; the owner rated the whole library (700 picks,
   `assets/animations/library/owner_picks.json`) — NEVER ask again.
3. 2026-10-13: procedural R6 = MADE FROM SCRATCH; loved clips are for CALIBRATION only (speed, amplitude, lag,
   timing, gates) — never splice, copy or mine their poses or gestures; one action at a time with a pick sheet first.
4. 2026-10-14: style walks from dataset ratios "all horrible"; every animation starts with a MOVE DOSSIER
   ("get more data on said animation you're building"); hit reactions solved from a real impulse "semi realistic, good job".
5. 2026-10-16: the roundhouse from its dossier was "correct but it isnt a nice animation" (the POSES), then "the arms
   awkward start to finish, the left leg doesnt just stay there ... not high quality" — the cause, measured: no R6
   VOCABULARY (loved R6 SLIDES every limb ~1 stud: legs up + forward = the bent knee, arms down; arms swing ~90 deg
   and WHIP ~45 deg at the strike; the support leg swings ~34 deg against the hips). The owner stopped picking:
   improve the pipeline; measure every candidate with `kit/anim/r6_vocab.py` before anyone sees it.

6. 2026-10-18: "i need you to start enfcorcig this type of proper loop so you dont mess up as much" - three keyed
   guesses at the katana underhip were rejected; the dossier run with REAL footage (13 measured suburi cycles) showed
   what all three lacked. THE LOOP, enforced by `kit anim` (proc_dossier gate):
   (a) a schema-2 dossier needs MEASURED evidence - a source with `measured` numbers + `real_s` on every moving phase;
   (b) every owner rejection (`kit anim verdict <Name> bad|horrible "<words>"` - record EVERY one, the moment it is
       given) blocks the rebuild until the dossier answers it in `owner_rejections` {date, quote, changed} - and a
       rejected move's dossier must be schema 2; so a "no" is never answered by re-keying blind;
   (c) a strike clip that misses any of its own dossier checks is not built.
   Per correction: record the verdict -> re-research (footage) -> update the dossier (mistakes, checks, the answer)
   -> build to the checks -> look at the render -> only then show the owner.
   (d) BLOCKING FIRST (AAA plan, board/plans/archive/2026-10-18-aaa-anim-gaps.md): a new or rejected move's first artifact is
   its BLOCKING - `kit anim block <Move>` (its key poses only, held, on the owner's R6_IK rig with the katana: bake
   <Move>Block, `kit anim edit <Move>Block`, bake, `--base`), its render (`kit anim look <Move>Block --rig R6`), and
   the owner moves what is wrong in assets/animations/<Move>Block.blend; `kit anim block <Move> --read` turns his
   changes into assets/animations/blocks/<Move>.edits.json, which the generator applies (strike.py key_edits).
   Limited animation (anime look): strike.py `step` {on, beats, imperfection} - poses held on 2s / 3s.
   UNARMED (2026-10-25, IronMountain): strike.py `unarmed: true`, `strike_hand`, `hands_frame: "torso"` - each fist
   keyed (rhand / lhand) where it sits ON the body, so the guard rides the turn and lean; steps, stamps and root
   motion go in the move's `feet` track (a `<side>_lift` arcs its own step only). Dossier body-blow measures:
   stamp_lead_s (NaN = the foot skated, never lifted), body_drive_studs, guard_hands_min_height_studs, arm_sink_max,
   hit_time_s. A side-on torso: the lead fist in front of its own shoulder (x ~ -0.85) and leg_twist_follow ~0.6.
7. 2026-10-24 (vault shared/orders): "the craft is no longer the weak link, CREATIVE DIRECTION is" - an ORIGINAL
   piece decides its direction BEFORE it is built: `kit anim direction <Piece> --new` -> assets/animations/direction/
   <Piece>.md (intent, the one idea, >= 6 references across media with take / leave, 3 pillars, bans, >= 3 directions
   that differ on >= 2 Axes - rhythm / read / effort / mood - each with a key-pose Frame rendered on the owner's rig);
   a dossier scaffolded from then on names its `direction` and the gate refuses it until the doc is READY. First:
   KatanaKaeshi (direction C built; the owner's pick open).
8. 2026-11-10: the kit home's Roundhouse round 5, built on the procedural route with no hand-keying, LOVED on every card
   ("I like the fluidity ... For the animation pipeline, good work"), with one note: "there's aggressive, there's calm,
   there is proper ... this is just a calm roundhouse kick". INTENT is a first-class input: `kit anim candidates <Name>
   --intent calm|proper|aggressive` (kit/anim/intent.py reads a strike's intent from the loved R6 strikes' own tempo
   thirds - his calm round reads calm 20/20; a kick is aimed by its strike window and its hips' lead, each intent samples
   its own efforts, and a candidate that reads as another intent is refused). His NAMED faults gate every generated
   weapon candidate (kit/anim/owner_faults.py: stilts, an arm-only cut, a flopping blade, legs wrung under a spin), each
   proven by `kit selftest` on the real clip he rejected for it. 2026-11-11: both roundhouse intents kept ("Animations are
   great as always"); the procedural weapon route then made a TWO-HANDED katana kesa (`kit anim candidates <Name> --dossier
   <move> --blade <gesture>`: a gesture with `two_hand` keeps both fists on the hilt every frame and runs the blade along the
   designed cut line; a weapon's intent is read on the blade's own sweep) - an aggressive katana passes the fastest katana
   cut he loved (arm speed 2,460 deg/s): his call, never a loosened check - answered 2026-11-11, "Keep it calm/proper":
   the katana stays calm / proper, inside the speed of the katana he loved.

## The AAA toolbox (board/plans/archive/2026-10-22-anim-aaa-gaps-v2.md - every item's state)
Making: `kit anim roto <picture> --as <Pose>` (click the joints -> an R6 pose) · `kit anim film <video> --as <Move>`
(your own phone video -> key poses) · `kit anim thumbs` / `diff` / `ab` (blind X/Y) · `kit anim polish` (root
outward) · `kit anim style <Set>` (guard, links, startup budgets) · `kit anim appeal [--cheat]` (line of action,
twinning = arms AND legs, balance, silhouette + blade seen % from the game camera, distance from the loved pose space;
--cheat = the upper-body yaw that opens a key to the camera). Move fields (strike.py): push / moving holds / step
(anime cadence) / impact dip / mask "upper" / smear / additive / camera keys / the marker contract (Swing,
ActiveStart, Hit, ActiveEnd, + Parry for a parry). Reactions: one proc_react dossier + `<Name>.dossier.json` specs
with `from` (Front/Back/Left/Right) and `hit` overrides = the runtime's `<base><Side><Tier>` matrix. Runtime
(src/kit; Studio-proven by tests/playtest/anim_layers + anim_client_layers + anim_parry + anim_combat_layers +
anim_motion_layers: inertialization, additive layers, the input buffer, camera tracks, smears, set.parry = { anim,
stagger } (the stagger lands with the riposte; the stun covers it), the reaction-matrix pick, the both-sided hit-stop,
ragdoll knockdowns, motion warping (turns toward the target, stops 3 studs short), look-at, the sword Motor6D,
afterimages - every runtime layer is proven; the smear slabs from carried travel (that place's avatar is R15, so an
R6 clip's own limb swing driving them is the one part not seen in Studio)).

Duels and cutscenes (all Studio-proven):
- `kit anim cutscene <script>` renders a scene from the kit's own clips ("clip", "react_clip" + "react_from",
  "counter" for a parry), swords drawn, fighters spaced by the blade.
- `--timeline` puts it IN THE GAME (KitAnimations.Cutscenes; a stale one fails kit verify):
  `Cutscene.play(name, anchor, { actor = Model })` runs the same plan on real R6 bodies - the kit's clips from their
  planned points, anchored roots, every hit-stop freezing every body, teleport gaps hidden, the planned camera +
  letterbox on a client, impacts on the kit Bus as Hit / Parried (`cutscene` set). `manual = true` + `handle.step(dt)`
  scrubs it (tests/playtest/anim_cutscene, anim_cutscene_client).
- Multiplayer: `Cutscene.broadcast(name, anchor, cast)` on the server; every client (late joiners too) watches it as a
  viewer on the shared server clock - the kit's AnimRoot client script already listens (anim_cutscene_net).
- OUT of Roblox: `kit anim export <Name> [--fbx] [--gltf] [--cutscene]` -> build/export/: the six parts (+ a sword
  clip's blade, + a cutscene's directed camera) as animated glTF nodes; Blender and three.js re-import it to 0.0000
  studs of the kit's FK.

## The route (8 stages)
| # | Stage | Its gate | Read |
|---|---|---|---|
| 1 | dossier | `kit anim dossier new <move>` / `check` — `assets/animations/dossiers/<move>.json`: phases with real + game timings, mechanics per phase, the cues that make it read, common mistakes, the R6 translation (no knee / elbow: what SLIDES, what the torso does), numeric checks; thin = refused; REAL FOOTAGE of the move: `kit anim dossier footage <move> <video.mp4>` (MediaPipe Pose, offline; clips via the vetted yt-dlp, private, `_artifacts/footage/`) measures every clean kick in it - timings, foot speed, hip + CHEST turn, pivot, lean, arms - numbers into the dossier, never poses (roundhouse: the footage moved 4 ranges and caught every shown candidate over-turning 114-148 deg and kicking 12-59 deg PAST the target) | `reference/01-*` |
| 1a | design | a STRING of attacks only: `kit anim design <Set>` - one page, cousins named, the owner's yes to the drawn page; a new move of the set is refused before it (the section above) | - |
| 1b | blocking | `kit anim block <Move> --sheet` - the key poses held, shown to the owner, his notes and his yes; `kit anim` and `kit anim candidates` refuse a strike, sword or kick move made after the rule without it (the section above) | - |
| 2 | author | from scratch: `proc_director` beat script -> gesture specs -> `pose_prior` -> `proc_r6` springs, dense 60 fps curves; calibrated bands from `proc_calib` (snap ≈ 0.2 s then hold; slides 0.6-1.7 studs; torso 1,100-3,300 deg/s at the hit; drag head 3 / arms 2 frames); the R6 VOCABULARY (`r6_vocab.json`: per-phase slides, the four loved ARM HABITS, the whip, a partial pivot); candidates differ by effort sliders / arm habit + whip / a blade's LINE — the efforts mapping 2 (2026-11-09: each effort moves the WHOLE body, and a fresh round first probes how far each effort REACHES on that move before a gate fails - up to 2.5x, cached; a blade's cut is also turned into other planes and the passing LINES each get their share of the sheet; a round records its mapping / reach / lines and a bred round keeps its parents') — `kit anim candidates <Name> --dossier <move> --n 8` (`--round K --parents a,b` breeds from picks; `--fresh --change "..."` after a rejected round); a REACTION dossier (`build.builder: proc_react` - a physical hit on a base idle, MuJoCo with an opt-in neck) gets candidates too: the four efforts become how hard / how sudden / the angle / how freely the body turns (`proc_candidates.react_genome`); its numbers come from the loved R6 reactions (`kit/anim/react_measure.py`, statistics only) - fight FOOTAGE cannot measure head reactions (lesson); a WEAPON dossier (`build.builder: fp_weapon`) goes to `proc_blade` (never `proc_strike`'s key poses - that stays for the owner's own keyed blocks): its clip's gesture (`build.gestures` -> `assets/animations/gestures/<g>.json`, kind blade: STAGE `reach` + `blade` per beat, square to each other - the R6 weld lays the blade square to the arm), the welded blade, a foot schedule (the step lands with the cut, the rear foot pivots), the free arm = a loved weapon ARM HABIT or a pose-prior mode + whip (`r6_vocab.py calibrate weapon`: the loved sword clips have NO legs - legs, torso speed and pivot come from loved full-body arm strikes), gated by the weapon vocabulary (`proc_blade.vocab_check`); footage numbers: `kit anim dossier footage <move> <clip> --kind swing|spin` | `reference/02-*`, `09-*` |
| 3 | gates | motion gates (feet, pops, seam, Hit on the strikers' peaks) + proc gates (readable, statue, face, floaty, robot_arm, jitter, copy_floor, style_band, frozen_limb — limbs a loved clip holds still, like combat legs, are listed UNGATED) + the VOCAB gate (a limb frozen below the loved minimum on slide AND turn fails; every measure under the loved p10 is a manifest WARNING — no loved clip can fail a gate) + the dossier checks (those an arm choice is not held to: warnings, never dropped) + MuJoCo — FILTERS, never a ranking; `kit anim judge <clip>` = the verifier (ONE difference + ONE edit vs the dossier, no score) | `reference/10-*` |
| 4 | picks | ONE action, 4-12 candidates as real-time GIFs (every 4th frame at 66 ms; a fast cut or a >= 2 turns/s spin every 2nd frame at 30/40 ms) from the PLAYER's camera with the fidelity line ("rig = clip within ..."); the OWNER picks (`kit anim picks <Name> --round K [--no-loved]`; no loved clip beside a card when it would be a design source - ruling 3; a standalone page with every gif embedded; each card shows the kit's own warnings - a limb or the blade below the loved range - under it: on 11-04 every shown card carried them and the owner rejected exactly those limbs); breed from the picks, never from catalog clips; GALLERY TUNING chooses each sheet (`kit anim candidates`): about 2.5x the gate-clean candidates are built and 8 chosen, spaced apart by MOTION (slider distance does not predict how different two candidates look; with nothing learned yet the sheet is the widest-spaced 8 the pool allows, each line keeping its share) - with the owner's own picks and rejections on earlier rounds of the SAME generator, half likely-good and half informative, and after an "All bad" the next round steers away from what was rejected; `--by <who>` when an agent picked the parents (never learned from); `kit anim gallery [<Name>]` = what it has learned. It cannot add variety the generator lacks: cousins that survive it need a wider generator; `kit anim plan <Name>` = where the action stands; the top of the sheet runs the round's checks from the owner's words (`kit checks run anim <Name>/round_K`: "cousins" = candidate spread, "stilts" / "arm-only" = the share of warned cards); `kit checks validate anim` = do the checks and warnings catch the owner's rejections and spare the picks - record the owner's picks so they can be proven | `reference/09-*` |
| 5 | studio | a pick becomes a GAME clip: `assets/animations/<Name>.dossier.json` ({dossier, sliders, arms, from_candidate} - copy the candidate's sliders; `kit anim` rebuilds it from tracked data with the efforts mapping, reach and line of the round `from_candidate` names, takes the variant / arms from the candidate when the spec has none, and REFUSES a spec whose settings are not that candidate's, a round that is gone, or efforts with no candidate and no `efforts` field - never a guessed mapping); `kit anim play <Name> --rig R6 --run --studio <id>` (the kit runs the probe in the NAMED Studio itself and records it - never a shared Studio; open your own on a copy of build/place.rbxlx); `kit playtest run owner_character_actions | moves_hitstop | anim_root_motion --studio <id>` (the owner's avatar as R6, the Moves hitstop, the root track) - server-owned dummies on a floor of their own, never the client-owned player | `reference/09-*` |
| 6 | verdict | `kit verdict anim <Name> <0-10> "<words>"`; promote only on ≥ 7; the lesson written | — |

Locomotion: never hand-key it from rules — `kit anim new <Name> --cycle <kind>` from measured key poses, checked by
SHAPE (`kit anim profile`, `kit anim sil`): approved R6 runs carry the legs forward by SLIDING them and pump the
forward hand across the midline. Library clips (`reference/08-*`) are the bar and the calibration, never a source.

## What never worked (`kit/knowledge/vault/anim/graveyard.md`)
Mocap / Kevin Iglesias / other engines folded to R6 · attacks authored from 8 key poses · a moveset matched to the
loved NUMBERS (angles are not poses) · splicing loved poses into a final · a taste model or same-model judge as the
bar · evolution bred from a punch pool · style walks by ratio-scaling · a gesture acted from its label (a statue at
1 deg/s) · FK legs on the IK rig, a copied armature, a camera behind the character · hand-set technique arms folded
over the torso (a clump at the hit) · the MEAN of many loved clips' arm directions (a T-pose nobody makes - cluster
into habits) · whole-pose appeal numbers (span / fill / twin sat inside the loved bands on rejected poses) · curve
texture / ease dips as gates (AUC 0.32-0.70 vs machine-eased copies: loved R6 snaps and holds).

## Traps (the full list: `lune run kit lessons anim`)
The rig faces +y in Blender (cameras at -y film the back) · the thigh `COPY_TRANSFORMS "IK"` sticks at 1.0 headless
(look_r6 mutes it and FAILS unfaithful renders) · Roblox CFrame.Angles composes X outermost · a `Torso` twist turns
the legs (twist UpperTorso on R15; the fold counter-rotates on R6) · foot contact at the sole centre · a one-frame
snap is by design (lift the pop gate there) · R6 reach 1.58 studs, shoulder->hand ≈ 2.1 · a slerp of a blade
direction goes round the side (a breakdown key at the arc's top) · gifs at real time · Blender 5.2's "Only Insert
Available" preference · Kimodo is not the route · diagnostics scripts must not shadow kit modules · leg IK that
REPLACES a slide (use `proc_director.leg_ik_keep`: the slide jumped 1.15 studs at lift-off) · a rotation range
measured from identity hides a raised arm's whip (measure from the limb's own mean) · a 60 fps gif's 17 ms frames
play ~20 % slow (every 4th frame at 67 ms) · one-shot ROOT tracks move the character only through `Anim.play`
(Meta carries them) · Motor6D.Transform reads back in single precision (compare with a tolerance; release a joint no
track drives) · a background Studio window plays at 6-10 Hz (time playtests off the move clock) · a weaker impulse is
not a light hit (the head whip saturates) · a cut swung in front of the chest hides behind the torso from the game
camera (check blade seen %, cheat the yaw, widen the follow-through - never a wind-up) · the verdict cap counts NEW
dossiers without the owner's own score (3), not the `verdict pending` list of inferred ones.

## Read next
`reference/04-rigs-*.md` · `reference/05-procedural-locomotion-*.md` · `reference/07-weapon-movesets-*.md` ·
`kit/knowledge/vault/anim/index.md` · `kit/knowledge/vault/anim/refs/kimodo-to-r6-translation.md` ·
`board/plans/archive/2026-10-13-proc-from-scratch-plan.md` · `ANIMATION_AUDIT.md` §9.
