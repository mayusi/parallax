<!-- reference for the parallax-anim route card; verbatim from the skill page (2026-10-16) -->

## R6 (the owner's rig; finished animations as the reference; generators fitted to them — the lane since 2026-10-11)

**THE LEARNING ROUTE (2026-10-11 night) - how the kit makes animations the owner calls good.** The owner loved a
finished community sprint on their rig ("AN AMAZING RUNNING ANIMATION") and rejected everything generated from a few
poses. Measured, a loved animation is DENSE CURVES (15-20 keys a limb, keyed every 60th of a second), so new work
starts from such curves and edits them like a graph editor - it never fills curves in from a handful of poses:
1. **Import at the native rate** (kit/anim/kfs_import.py never downsamples: the loved sprint was imported at 30 fps and
   lost every other frame - the "legs snap" the owner saw).
2. **Measure in the style book**: `lune run kit anim book` (kit/anim/book.py) - every R6 clip with one ruler (key
   density, snaps, body drive, speed, snap, holds, startup / active / recovery) beside `assets/animations/verdicts.json`
   and what separates loved from rejected, per kind. Record every owner verdict: `lune run kit anim verdict <Name>
   <loved|good|ok|bad|horrible> "why"`.
3. **Fix snaps**: `lune run kit anim snaps <Name>` finds single frames that jump far beyond their neighbours (kit/anim/
   snaps.py); `pose-from ... --despike` re-spaces them (path kept). On attacks a strike IS fast: report, do not fix.
4. **Derive, don't generate**: `assets/animations/<Name>.derive.json` + `lune run kit anim derive <Name>` (kit/anim/
   derive.py): despike, retime, amplify (about the joint's mean pose, gimbal-free), posture, shift (drag), layer
   (upper body over legs), mirror, STYLE transfer (posture bias + dynamics of a loved clip), blend, chain, breathe,
   hold, hitstop, still, extend, concat, TIMING transfer (a blocked-out move re-spaced along its own path so its
   motion accumulates as a loved strike's does: GSSlash1 with RefBwA2's timing starts in 0.167 s, not 0.283 s).
   OVERLAP: a Holden spring follows the torso's turning and the head / arms inherit its lag (defaults 0.03 s, 0.3:
   ~11 deg of head lag on a 166 deg whip, ~2.6 on a sprint) - follow-through without hand-keyed offsets. The result goes onto the owner's rig as REDUCED keys (`--reduce`, curve
   simplification: an editable file with the animator's structure; the head reduced in world space).
5. **Movesets as one thing**: `assets/animations/movesets/<Set>.json` + `lune run kit anim moveset <Set>` (kit/anim/moveset.py) - one
   guard, the moves (derive recipes), the chains. Checked as a SET: chain seams (<= 8 deg), every chain starts and
   ends in the guard, the tempo of each action, snaps; a contact sheet (start / anticipation / strike / follow-through
   / end per move) and a chain preview (<Set>Chain<k>: the combo back to back, as the player sees it). Example: the
   Brawler set (assets/animations/movesets/Brawler.json): the 60 fps DevForum combat pack's A1 -> A2 -> A4 hand-offs
   (0.1-0.2 deg seams), A3 as the finisher with a 7-frame hitstop and a recovery to the guard, a breathing guard idle,
   block, two hit reactions, the loved sprint.
   **Compose is a last resort.** A double strike composed from loose poses of two moves was judged 33/100 by a fresh
   reviewer: their torsos faced 115 deg apart and the body spun between them in 3 frames, and a smoothstep plateau held
   the jab 7 frames. Join REAL strikes instead: `trim` + `concat` with a `crossfade`. compose now lengthens any segment
   faster than its source clips and warns on a facing flip.
   **Judge every new move with a fresh reviewer BEFORE the owner sees it**: `kit anim judge <Name> --rig R6` -> a fresh
   Opus agent reads PROMPT.md and the two images -> `--record` the verdict.
   More ops born from judged gaps: `tempo` (piecewise time warp around the strike: a longer coil, a shorter recovery;
   keep `window` ~1 frame so the stretch lands on the real wind-up, not a pre-roll), `unhold` (cut dead frames),
   `declip` (an arm through the torso / head - `python kit/anim/clipping.py <clip>`, separating-axis on the R6 boxes -
   turned and slid out about the shoulder by the smallest move, smoothed; put it LAST, after chains), `amplify` on
   the Torso / Head below 1 (calm a whole-body whip: a 165 deg turn to 65).
   **The judge loop, measured (2026-10-11):** the same strike re-edited six times scored 3.2 / 3.7 / 3.8 / 3.4 / 3.5
   (fresh Opus judges; their noise is about +-0.4) while the owner-LOVED sprint scores 4.3 - so the judge is harsh
   but ranks sensibly, and edits plateau at the SOURCE's pose design (an arm stuck out sideways, no weight shift
   cannot be edited into a great punch). Better source data, or authored poses, is what moves past it.
   **Authoring from scratch WORKS with the judge loop** (CraftCross, assets/animations/CraftCross.pose.json - a cross
   punch keyed on the owner's rig from the judges' craft rules): fresh-judge scores 3.5 -> 3.5 -> 3.8 -> 4.2 -> 4.5
   -> 4.5 -> 4.5 over seven versions, above the owner-LOVED sprint's 4.0 on the same prompt. What moved it: arms
   TORSO-RELATIVE (swing / out / slide - root-relative hand targets cross the chest when the torso turns); the Hit
   on the fastest frame AND at full reach (no arm drag at the strike); a hip-lead breakdown so the strike travels
   over 4 frames; lean <= ~15 (more reads as falling); a coil that turns AWAY further than the guard; a real
   recovery (torso home before the arm, no dead hold); the head dipping into the Hit. **R6 has NO WAIST:** the
   torso is the hips, so a big torso turn swings both legs (judged a whole-body snap) - keep the turn ~45 deg and
   let lean + arm carry the punch. The judge prompt now states R6's limits (rigid limbs, slides for bends, no waist).
   **The rules are code now:** `lune run kit anim new <Name> --strike jab|cross|hook|uppercut` (kit/anim/strike_r6.py)
   writes an authored strike on the set's guard. The Craft set (assets/animations/movesets/Craft.json, `kit anim
   moveset Craft`) was judged in four rounds to jab 4.5 / cross 4.5-4.8 / hook 4.2 / uppercut 4.5 (the loved sprint:
   4.0), chain seams 0.6 deg. Judges disagree at that level (an uppercut "tips back" one round, "pitches forward" the
   next): ~4.5 is this judge's noise floor for R6 - the OWNER's verdict decides from there.
   Defence kinds on the same guard: `--strike slip|block|hit_react` (slip 3.5 -> 4.0, block 3.8 -> 4.2, hit reaction
   3.5 -> 4.4 after one or two judged fixes). HEAD BEHAVIOUR IS PER KIND: a strike's head follows 70% of the turn,
   a slip's head RIDES the torso (judged: "the neck cancels the lean"), a hit reaction keys its own head (thrown back
   first, held, home last) - one head rule for all moves was the slip's and the reaction's top fault.
6. **Look**: `kit anim sil` (silhouettes, arcs and the SPEED CURVES with snaps circled) before any textured render;
   then on the owner's rig.
7. **Runtime weight**: src/kit/AnimFeel.luau (Holden's critically damped spring, the Overgrowth lean from speed and
   acceleration) - `Anim.locomotion(character, set, { lean = true })` tilts the R6 RootJoint into acceleration.

**THE WORKFLOW (research 2026-10-11, `board/plans/archive/2026-10-11-anim-research.md`: sources, measurements, per-type recipes).**
1. **Measure against an approved reference FIRST**: `lune run kit anim profile <Name> --vs <Ref>` (kit/anim/anim_profile.py).
   It reports swing amplitudes, arm/leg opposition and drag phases, bob, twinning, SNAP (peak/mean speed: a sine
   glides at 1.57, finished R6 runs measure 2.5-2.9), ground speed (the play rate at a WalkSpeed so the feet do not
   skate), SHAPE (where the forward hand goes: from the midline and how high; the front foot's reach; the heel kick)
   and FAULTS (a limb swinging over the top, an arm swinging WITH its own leg). The gaps come out as sentences.
   ANGLES ARE NOT ENOUGH: RigRun2 matched the sprint's every angle number and was "genuinely horrible". Its legs
   splayed and its arms flew like an airplane, and only the shape numbers and the silhouettes show that.
2. **Start from what the owner approved**: `lune run kit anim pose-from <Ref> --as <Name>` (kit/anim/pose_from.py)
   turns any R6 clip into editable key poses on the owner's rig (exact decomposition: RefSprintRig is CommunitySprint
   on the rig at distance 0.2, 0 gaps).
3. **Key only what moves at that key** (a field left out interpolates; repeat a value to hold). **Limbs at their
   EXTREMES with in-out eases** (quad_inout ≈ the finished runs' snap; cubic is snappier), and a **BREAKDOWN at the
   bottom** of any swing over 180° (two extremes interpolate the short way - OVER THE HEAD).
4. **The drag hierarchy**: `"offsets": {"arms": 1, "head": 2}` (frames each group trails the body; loops wrap
   seamlessly). Nothing starts and stops on the same frame. **Break the mirror**: the second step differs a little.
5. **Runs**: plant the stance leg at DOWN (`plant`), give contact a set body height with the front leg SLIDING forward
   (the R6 reach: the finished sprint slides its contact leg 0.6-0.76 forward instead of dropping the body), and clear
   both feet in flight (`plant: both, clear`). Planting the reaching contact leg inverts the bob (lowest at contact).
6. **LOOK at the silhouettes first**: `lune run kit anim sil <Name> --vs <Ref>` (kit/anim/silhouette.py, seconds, no
   Blender) draws side and front silhouettes plus the hand and foot ARCS, with the reference underneath at the same
   cycle shares. Check that the legs stay under the body, the forward arm pumps ACROSS the body to chest or face
   height, the lean is clear, and the arcs loop smoothly. Then render on the owner's rig (`kit anim look <Name> --rig
   R6`), front three-quarter + side.

**LOCOMOTION (walk / run / sprint): never hand-key it from rules.** Use `lune run kit anim new <Name> --cycle
walk|run|sprint [--params '{"scale": 1.1, "cycle": 36, "asym": 0.94, "lean": 2, "arm_cross": 0.2, "knee": 1.1,
"offsets": {"arms": 1}}']`. It rebuilds the cycle from the MEASURED key poses of an approved clip
(kit/anim/cycle_r6.py, presets in kit/anim/cycle_presets.json, learned with `python kit/anim/cycle_r6.py learn <clip>
--kind <k>`). Each phase of a step stores the torso's lean, turn and tilt, each leg as SWING + SLIDE (the R6 knee: the
swinging leg slides up and forward at passing), each HAND's position (the forward hand across the body at chest to
head height), the head's facing and the lowest foot's height. Then `kit anim <Name>`, `kit anim profile <Name> --vs
<Ref>`, `kit anim sil <Name> --vs <Ref>`, then look on the rig. A new approved reference becomes a new preset with one
`learn`.

**THE ROUTE FOR R6 ATTACKS (2026-10-11): author key poses ON THE OWNER'S RIG.** `lune run kit anim new <Name> --pose`
-> `assets/animations/<Name>.pose.json` -> `lune run kit anim <Name>` -> kit/anim/pose_r6.py opens
assets/rigs/R6_IK.blend, turns its IK legs on (SoftIK.* slider 2, FK off), keys its CONTROLLERS from the key poses,
evaluates the rig every frame and bakes the parts' Motor6D transforms into the clip (checked: every part centre from
the clip's FK within 0.01 studs of the evaluated rig, or the tool fails), and saves `build/animations/<Name>.r6.blend`
(the rig, the motion as an action on its controllers, IK on, a greatsword on the right fist). `kit anim look <Name>
--rig R6` renders THAT file as it is (`--posed`). `kit anim edit <Name>` copies it to assets/animations/<Name>.blend:
the owner edits in Blender, and from then on the .blend is the source (kit/anim/bake.py reads the rig's kit_parts,
settles its driver cycle, keeps the sword path, loop and priority) - re-baking an unedited copy reproduced the pose
clip within 0.0005 deg (measured once, 2026-10-11; no automatic test: it needs Blender). The left hand on the hilt
is KEYED per frame in that file, not constrained: re-pose Arm.L after changing Arm.R. Why this and nothing else: every attack built from generated keys (strike.py), re-armed
mocap or a borrowed punch body with a sword glued on was rejected; none used the rig's IK (feet planted, a lowered
body keeps the feet planted while R6 legs, which never bend, sink into the torso; FK legs under a lowered body
go through the floor), and
the R6 look filmed every one of them FROM BEHIND (cameras at -y; the rig faces +y: Roblox -z -> Blender +y, the
right arm at +x). The key-pose file, in STAGE axes (x right, y up from the floor, z forward, ROOT-relative):
- `root`: `turn` / `pos` - the whole character (Main Controller: body AND feet); a spin turns the root in keys <= 90
  deg apart, the arms hold the sword out and the root carries it round (GSSpin).
- `body`: `pos` (dy < 0 crouches: the IK legs stay vertical and sink into the torso - spread the FEET for a wide
  stance), `lean` + forward, `turn` + to the right, `tilt` + right shoulder down.
- `head`: `look` (a direction held on target while the body twists), `tilt`.
- `right_arm`: `hand` + `blade`. The BLADE is exact: an R6 arm has no wrist, the blade leaves the fist at the grip's
  fixed angle (`sword.grip_pitch`: 0 = perpendicular to the arm, the Roblox tool default; 60 = the blade continues
  the arms' line, a two-handed greatsword's), so the solver picks the arm on that angle's cone nearest `hand`; the
  hand lands where the blade allows (`"lock": "hand"` inverts it). Reach is 1.58 from the shoulder pivot, + up to 0.5
  of arm slide (R6 animators slide arms too).
- `left_arm`: `"hilt"` = solved onto the hilt `sword.spacing` below the right fist EVERY frame (keyed per frame, so
  the grip holds mid-swing), `{"on_blade": d}` = the palm braced `d` studs up the BLADE from the right fist, every
  frame (a greatsword block: the blade flat across the face, two hands on the hilt there would fold rigid R6 arms
  across the chest; a key going "hilt" -> on_blade slides the hand along the sword), or `hand` / `aim` / `rot` / `swing`.
- `right_foot` / `left_foot`: `at` [x, z] on the floor, `lift`, `turn` - the IK targets.
- fields a key leaves out are held field by field (an arm key with only `blade` keeps its `hand`; a new `hand` / `aim` / `rot`
  replaces the held placement). Gates: the kit's defaults - the GS set passes them unchanged.
- `"legs": "fk"` (the rig as shipped: SoftIK 0, FK box on) for swinging motion - runs, walks: `right_leg` / `left_leg`
  and arms as LIMB SWINGS `{"swing": deg (+ forward / up), "out": deg (+ away from the body), "twist": deg, "slide": [x, y, z]}`,
  torso-relative from the joint pivot; `body.plant` (`right` / `left` / `both`) solves the body height so that leg's
  lowest point is ON the floor (`clear`: this far off it, for a run's flight) - per key, never held. RigRun is built so:
  per step contact / down / passing / flight, the legs SLIDING up into the torso (the R6 knee) and forward on the knee
  drive, the arms sliding down-forward at the top of the pump (the R6 elbow) - the vocabulary of the community R6 runs.
- per key `ease` shapes the segment FROM it: bezier (auto), linear, constant, `<sine|quad|cubic|quart|quint|expo|circ|
  back|elastic|bounce>_<in|out|inout>`; `f` in frames at `fps` (60 like the owner's file). Fields left out are held.
Check feasibility before rendering, without Blender: `python kit/anim/pose_r6.py --check assets/animations/<Name>.pose.json`
(per key: where the right fist lands, its offset from `hand`, the left hand's gap to the hilt, the tip's height). The set: GSIdle (loop), GSSlash1
(diagonal), GSSlash2 (horizontal backhand), GSSlam (overhead), GSSpin (360 heavy). Timing that reads (60 fps):
wind-up 12-16 f, a 4-8 f hold, the strike in 6 f (quad_in into a linear breakdown into the Hit), expo_out after the
Hit, overshoot 8-10 f, recovery 20-25 f to the guard. The older routes below (gaits fitted to references, re-arm,
keys from references, strike.py authoring, the feel pass) still build; for attacks they are superseded.

**The owner's rig, as built** (assets/rigs/R6_IK.blend). **Read `assets/rigs/R6_IK.md` first** (and `kit/anim/r6_rig_model.py`: the rig as equations, within 0.0003 studs): every object, bone,
control, constraint, driver (seven are dead leftovers), the IK leg mechanism, the SoftIK BLEND slider (0..2, IK
influence = slider / 2; the file ships FK), Head.001 not inheriting the body's turn, the camera rig, the 6x2x6 target
block in front, and the ORIENTATION-TEMPLATE texture (FRONT/BACK/L/R/UP/DOWN on every face, a face on the head) that
the R6 look renders with (`--flat` for the old flat colours). The full dump: `kit/anim/rig_dump.py`. It is a Roblox Blender-Animations plugin rig
(`__RigMeta` carries every Motor6D's C0/C1; studs = Blender units, Z up, the character faces +Y, HumanoidRootPart at
z 3, the floor at z 0) with an animator's control layer on top. The part MESHES hang off deform bones named like the
parts (`Torso`, `Head`, `Right Arm`, …; the Torso mesh off `Body`), and those bones are DRIVEN by COPY_LOCATION +
CHILD_OF constraints from CONTROLLER bones: `Main Controller` (root), `Body` (torso, head at the root), `Head.001`
(neck), `Arm.R` / `Arm.L` (shoulders, pointing down), legs in FK `FKLeg.R` / `FKLeg.L` (hips, euler XYZ) or IK
(`Foot.R` / `Foot.L` controllers on the floor, `Knee.R` / `Knee.L` poles, a 2-bone chain `Bone.003` / `Bone.001`,
`SoftIK.R` / `SoftIK.L` custom prop `FK` switching the `Leg.R1` / `Leg.L1` copy-transform constraints through
drivers; a driver cycle - SoftIK is a child of the leg it switches - settles on a second depsgraph update). The rig's
own action keys ONLY the controllers. So does the kit: a pose source keys them with IK on (above); `kit anim look
<Name> --rig R6` of any OTHER clip keys the clip on the controllers in FK (a part's world delta applied to its
controller, whose head sits on the part's joint), leaves every constraint and mesh alone, and saves the posed rig as
`build/animations/<Name>.r6.blend`. The look's cameras stand IN FRONT (+y) and frame the BODY, not the sword's sweep. (Driving the deform bones with the constraints muted rendered the
same pixels - checked on RbxTwoHandSwing - but bypassed the rig; never do that again.) The rig's `Camera` armature
reproduces a Roblox camera (FovPart, vFOV); the look uses its own cameras.
The owner judges R6 only, on THEIR rig (VETLOG 2026-10-11), classic yellow/blue/green, from the front. Show the
owner nothing else.

**The learning loop (the owner, 2026-10-11: "find references, vet them, download them, learn from them"):**
1. **Find** finished R6 animations by Roblox animators: DevForum Community Resources posts with an attached `.rbxm`
   (the post's own upload downloads; `assetdelivery` needs a login for anything not Roblox-owned), Roblox's own
   defaults (Roblox-owned, public: walk 180426354, idle 180435571/180435792, jump 125750702, fall 180436148, climb
   180436334). Vet: the post, the replies' verdicts, the stated terms; a VETLOG row; `kit/anim/kfs_dump.luau` lists
   the file's KeyframeSequences and flags any script (nothing runs). Paid packs (BuiltByBit / robloxanimations.com
   sword packs, 80+ R6 clips, DRM-free rbxm) are the owner's call. On disk: `_downloads/r6_community/` (the DevForum
   '[R6] Run + Walk' pack — Walk + Sprint, "insanely good", free use; azazinchic's 'Basic run'), `_downloads/roblox_r6_defaults/`.
2. **Import as it is**: `lune run kit anim import <file.rbxm> --clip <KeyframeSequence> --as <Name>` →
   `assets/animations/<Name>.import.json` → kit/anim/kfs_import.py: an R6-NATIVE clip (joint-space Pose CFrames →
   character space, the engine's easing per Pose, markers → events, Loop/Priority kept); no fold, no retarget. Its
   gates only report (`foot_slide` 1.0, `pop_deg` 60, `loop_seam_deg` 5: R6 feet skate, loops nearly close). Set
   `speed` in the spec for the runtime. Look at it on the rig: that is the bar.
3. **Measure**: `lune run kit anim measure <Name> [--vs <Other>]` (kit/anim/measure.py) → per joint the pitch /
   yaw / roll / position curves over the cycle (24 phase samples), ranges, where each peaks, the relations (head
   yaw vs torso yaw, arm vs leg, torso yaw vs leg, lean, drop), and with `--vs` the per-joint distance after the
   best phase shift. What the references taught (2026-10-11): legs are pendulums of +-45..+-100 degrees that
   TRANSLATE (the swing leg 0.5-0.7 up into the torso and 0.8-1.3 forward, the landing leg reaching down, the
   stance leg dragging back); arms against the same side's leg, +-20 with a 0.3 translation in a walk, pumping to
   155 degrees with the hand dropping 0.85 and reaching 0.7 in a sprint, elbows out; a constant lean of 6-17,
   the torso 0.1-0.2 low, twist +-6 (walk) to +-18 (sprint) AGAINST the leading leg; the head counters the twist
   exactly (corr -1.00) and the lean fully; cycles 0.8 s (walk) / 0.57 s (sprint); keyed linear at 60 fps.
4. **Fit the generator**: `lune run kit anim new RunR6 --gait run --rig R6` → kit/anim/gait_r6.py (walk run sprint
   idle), every one of those findings a parameter (`amp_fwd/amp_back`, `knee`, `reach`, `reach_down`, `drag`,
   `arm_fwd/arm_back/arm_in/arm_out/arm_reach/arm_drop`, `lean`, `drop`, `forward`, `twist`, `sway`, `bob`, `rise`,
   `overshoot`, `head`, `look`, `cycle`, `duty`, `speed`); the stance sole runs at EXACTLY the ground speed inside
   `band` of the vertical on a world ground line (a twisting torso would carry a planted sole sideways: the legs
   swing in the world's forward plane), floats beyond it as every R6 foot does. `lune run kit anim fit <Name> --to
   <Reference>` (kit/anim/fit_r6.py) sets the parameters from the reference's curves (a measured first guess, then
   coordinate descent on the distance; `fitted_to` with the residual per joint is written into the .gait.json) and
   rebuilds. The residual is honest: what the generator cannot do (a sprint's arm roll curves) stays in the
   reference. Tests: kit/test/python/test_anim_r6.py, test_anim_fit.py.
5. **Re-arm** a finished clip for a weapon: `lune run kit anim rearm <Name> --from <Clip> [--length 5.2] [--grip 0.8]
   [--grip-pitch 20] [--lag 0.05] [--hands 2]` → `<Name>.rearm.json` → kit/anim/rearm.py keeps the body (torso,
   head, legs: the mocap's or the animator's timing), puts the hilt in the right hand (an R6 arm has no wrist: the
   blade's direction is the arm's turned by `grip_pitch`), solves the second hand onto it (the two-sphere solve
   moves the hilt the least), gives the steel momentum (`lag` delay + a one-pole `inertia`: a whip in the source
   becomes a sweep; a two-hand solve on a raw whip snapped the off hand half a turn), re-times Hits to the blade
   tip's peaks, draws the blade in the look. The Claymore set (ClaymoreLight1/2/3, ClaymoreCombo, ClaymoreStance,
   ClaymoreGuard, ClaymoreDash from UAL2's Sword_Dash_RM with its root travel, ClaymoreHeavy from UAL1's
   Sword_Attack) is mocap re-armed this way; ClaymoreThrust is strike.py technique keys (no mocap thrust on disk).
   The metric judges a Hit against the STRIKERS' peaks (the blade, the hands), not only the fastest part: a dash
   moves the head fastest. The look GIF freezes on every Hit by the clip's `feel.hitstop` (default 3 frames). Roblox's own R6 gear attacks (RbxTwoHandSwing,
   RbxSwordThrust, RbxNinjaSlash, RbxDualSlash, …; VETLOG) are the grip-convention references: arms only, 5-7 keys.
6. **Keys from a reference** — the loop that keeps the animator's body and lets you write the weapon:
   `lune run kit anim keys <Name> --from <Reference> [--every 2] [--length 5.2] [--grip 0.8] [--grip-pitch 20]`
   (kit/anim/keys_from.py) reads a finished R6 clip's torso (pitch / yaw / roll / position), legs (keyed outright:
   `right_rot` / `left_rot` + offsets, `legs: "keyed"`), head look and the hilt where its right hand is, at the
   animator's turning frames (`--every 1`: every frame; the regenerated body is within 0.2 of the reference, 1.0
   at `--every 2`), into `<Name>.move.json` for strike.py. Edit `grip` / `dir` keys for the weapon's arc; the
   body stays. `kit anim measure <Name> --vs <Reference>` reports what moved. Finished R6 attack references on disk
   (VETLOG, from the DevForum's own uploads via its search API — Creator Store assets need a login, GitHub has
   none, Payhip/robloxanimations 'free' packs need a checkout): RefFinisher / RefWindUp / RefSpin (KingAlijahforever's
   Free Friday whirlwind), RefSwing1/2/3 (melee, arms only), RefFFWalk / RefFFIdle, RefEngRun / Walk / Idle.
7. **Feel** — the pass that separates a finished attack from a correct one (the owner rejected every attack whose
   body was right but whose TIMING was mocap-even): `lune run kit anim feel <Name> --from <Clip> [--anticipation
   1.5] [--snap 0.55] [--hitstop 3] [--overshoot 0.18] [--settle 4] [--recovery 1.15]` → `<Name>.feel.json` →
   kit/anim/feel.py retimes the clip around every Hit (the clip's events, else the strikers' speed peak): the
   0.2 s before the strike runs `anticipation` times slower (a hold the eye reads as intent), the 0.08 s into the
   hit runs `snap` times faster (one frame of travel - the pop gate is lifted to 130 deg for that frame, as finished
   R6 attacks turn the torso 40-110 deg there), the hit pose is held `hitstop` frames IN the clip, the pose then
   keeps going past the hit by `overshoot` of the last step and settles over `settle` frames (follow-through), the
   0.45 s after run `recovery` times slower, named joints trail by N frames (`lag`, default the head by one). The
   blade path and root track are retimed with the body; the Hit event moves to the held frame. Compare in the
   look: `kit anim look <Name> --rig R6` beside the source. Built after re-arm clips (it reads their blade).
   Tests: kit/test/python/test_anim_feel.py.
8. **Author** with strike.py (superseded for attacks by the pose route at the top of this section): a `.move.json` whose keys are what an animator thinks in -
   the torso (`pitch` + = lean back, `yaw` + = turn left, `roll`, `pos`), the HILT (`grip`, character axes, kept
   within R6 reach: ~1.5 studs of each shoulder, so near the chest - the BLADE does the reaching) and the BLADE
   DIRECTION (`dir`), both arms solved onto the hilt (`hands: 2`, `lag` / `inertia` 0 while authoring), the FEET
   as targets (`right` / `left` xz, `_h` lift, `weight`; the leg solver plants them under the moving torso - never
   key leg rotations under a bent torso: R6 legs are the torso's children, a 40 deg bend cancels a 45 deg swing),
   the head (`look_pitch` / `look_yaw`, looking at the target on the cut). Pose order for a cut: stance (blade up-
   back over the shoulder) -> wind-up (behind the head, torso twisted and leaned back, weight back) -> a BREAKDOWN
   at the top of the arc (blade straight over the head toward the front: a slerp from up-back to down-front-left
   goes round the side without it) -> the cut (torso bent forward and twisted the other way, the lead foot lunged,
   tip just above the floor) -> follow-through low -> slow recovery. Check the numbers before the render: hand and
   tip positions per frame from `C.world_frames` (a stance that looked right in words had the blade pointing
   down-forward). Then `kit anim feel` on top. GreatswordSlash1 is the first one built this way.
9. **Use** the reference itself when it is the best thing on screen (CommunityWalk, CommunitySprint are kit assets
   like any other, credited in VETLOG); build the rest (attacks, the greatsword set) in the measured vocabulary.
