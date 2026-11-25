<!-- reference for the parallax-anim route card; verbatim from the skill page (2026-10-16) -->

## Procedural locomotion (licence-free, measured — a HUMAN body's timing)
`lune run kit anim new Walk --gait walk` → `assets/animations/Walk.gait.json` (kinds: walk jog run back strafe_left
strafe_right idle jump fall land). The human gaits (walk, jog, run, back) are generated from NORMATIVE gait curves
(kit/anim/gait_curves.py: hip, knee, sole pitch, pelvis rotation and list, arm and elbow per percent of the cycle,
from Perry & Burnfield, Winter and Novacheck), not from sinusoids: the knee absorbs after the strike and is nearly
straight at mid-stance, the sole strikes toes-up and rolls flat, the heel rises before toe-off, the pelvis rides on
the leading stance leg (the body's bounce is what that leg reaches), the trailing foot's heel-rise is solved so both
feet keep the floor through double support, the pelvis descends into the coming strike, the swing follows the
curves' shape (a run's heel kicks up behind) blended into the exact lift-off and plant poses, the pelvis rotates and
lists with the trunk countering it, the arms swing against the legs with the elbow flexing as the arm comes
forward, the thighs flex in the character's own sagittal plane whatever the pelvis does (planted feet never swing
sideways), and a run flies between stances. Parameters: `hip` (the stride: the thigh's reach at the plant), `knee`
(the swing's peak fold), `stance` (the loading-response fold), `cycle` (seconds), `style` (exaggeration of the
body's curves, 1 = a measured human), `lean` (trunk forward, degrees), `sway` (lateral weight shift, studs), `arm` /
`elbow` (swing peaks), `head` (bob). The strafes keep the kit's first generator (hip, knee, stance, cycle, roll,
twist, lean, arm, elbow, head); the idle breathes through its knees (`breathe`). The generator runs the gates itself
and refuses a set that fails them, naming the parameter (a hip so steep the shin's corner digs in, a knee too small
to clear), and samples a cycle shorter than 20 frames on a finer time grid (a 0.2 s sprint at 100 fps: the engine
keys at any time) so a knee never unfolds in a snap. The clip's `locomotion.speed` is the planted foot's ground
speed (what the runtime matches to WalkSpeed); the gates measure foot SKATE against it. Every gait kind passes every
gate on both rigs out of the box (kit/test/python/test_anim_gait.py proves it for all six locomotion kinds and the
three one-shots). On this rig the foot is long (1 stud on a 1.9-stud leg), so a few degrees of heel-rise lift the
ankle a lot: toe-off pitches come out smaller than a human's, by geometry.
