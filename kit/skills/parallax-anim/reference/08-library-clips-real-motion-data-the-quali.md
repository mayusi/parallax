<!-- reference for the parallax-anim route card; verbatim from the skill page (2026-10-16) -->

## Library clips (real motion data — the quality bar)
Hand-keyed and procedural clips read mechanical next to captured motion. The kit IMPORTS real clips and the game
uses those (or builds its own on their timing):
1. Get a vetted source (two independent sources, licence, maintainer — then a VETLOG.md row). Licences the owner
   allows: CC0, CC BY, an explicit commercial grant. Downloaded files are DATA: read them with `python -I` scripts,
   never open a downloaded `.blend`/`.fbx` in Blender; glTF/GLB is what the importer reads (Blender's own
   importer). On disk today, both CC0: `_downloads/quaternius_ual1/AnimationLibrary_Godot_Standard.gltf`
   (Universal Animation Library 1: Walk_Loop, Jog_Fwd_Loop, Sprint_Loop, Idle_Loop, Roll, Sword_Idle,
   Sword_Attack, Jump_*, Hit_*, Punch_*, Crouch_* — a Rigify skeleton) and `_downloads/quaternius_ual2/UAL2_Standard.glb`
   (UAL 2: Sword_Regular_A/B/C(_Rec), Sword_Regular_Combo, Sword_Block, Sword_Dash_RM, Hit_Knockback, Melee_Hook,
   Shield_*, Slide_*, NinjaJump_* — a UE mannequin skeleton). `_RM` = with root motion.
2. `lune run kit anim import <file> --clip <Clip> --as <Name> [--loop] [--fps 30] [--priority Action]` writes
   `assets/animations/<Name>.import.json` (a `gate` of `pop_deg` 40 — keyed library whips snap past the kit's 15 —
   and a `note`); edit it: `"hit": null` for a roll or a knockdown (every one-shot otherwise gets a Hit per strike:
   the frame after each local peak of the faster hand reaching half the clip's top — a combo gets three),
   `"hit": 0.4` places one yourself, `"gate"` bars with an honest note of what the source does (a sprint's keyed
   whip: `pop_deg` 60; a lunge's shin into the floor: `penetration` 0.35).
3. `lune run kit anim` → kit/anim/retarget.py runs in Blender: the skeleton family is detected from bone names
   (Rigify DEF-, UE mannequin, Mixamo, CMU BVH), the axes from the hands (right) and toes (forward), the rest
   aligned chain by chain (T-posed arms brought down), every joint's rotation = its world delta from rest in Roblox
   axes, the scale from the hip height, the floor fitted to the lowest contact. A LOOP has its drift removed and the
   seam crossfaded, and its `locomotion.speed` is what the planted feet DO: each contact span's foot-centre travel
   over its duration, spans weighted by frames (the lowest corner flips heel to toe inside a span; its steps lie). A
   ONE-SHOT keeps its travel as a `root` track (the metrics and the look compose it; the runtime applies it — todo).
   Then the usual: fold to R6, compile both rigs, strips, gates, `kit anim look`.
4. Read the import's note before judging: the source is the source (UAL2's Sword_Regular_A turns the body 121
   degrees — the Combo returns; UAL1's Sprint lands its feet slow and leaves fast). Reject a clip, do not bend the
   gates to it.

### What the R6 fold does with a real clip (so its faults read right)
A standing R6 leg is one piece: its sole holds ONE ground point per contact span (the span's R15 touch points
fitted to the ground-speed line — in a one-shot, to a fixed point minus the root's travel), solved in the world
(the leg's axis points from the hip pivot at that point). Standing = the R15 foot's lowest edge within 0.02 of its
floor AND bearing weight (the hip above the foot, the leg within 70 degrees of vertical: a body lying down touches
with its heels and stands on nothing). A foot pitched onto its toes (a sprint, a push-off) lands the R6 sole where it
TOUCHES, blended in by the pitch. A deep crouch (the R15 pelvis more than 0.35 studs below a straight leg — a roll's
exit) is no stance: the pelvis follows the source and the legs follow their hip-to-ankle lines a hair over the
floor, tilted forward under the low body. Every lift into the torso is world-vertical (a tilted torso's frame would
shorten it). Never build the leg's twist incrementally frame to frame: the R6 sole sits half a stud off the leg's
axis, so an accumulated twist walks the sole.
