# Kimodo (human motion) -> R6: what is known (the spec)

Written 2026-10-13 from two days of owner briefs, 179 pairwise votes and 153 absolute scores
(assets/animations/verdicts.json "pairwise" / "absolute"). Every candidate translator is judged against this.

## The goal
A text prompt -> Kimodo (nv-tlabs/kimodo, SOMA 77-joint human motion) -> a GREAT-looking R6 animation, automatically.
The owner's verdict is the only measure of "great". Gates (pops, floor, foot slide, loop seam) and "follows Kimodo"
are FILTERS before the owner, never the score.

## Owner rules about R6 (stated, not inferred)
- R6 only, judged on the owner's own IK rig (assets/rigs/R6_IK.blend) - `kit anim look --rig R6`.
- "One leg is ONE leg": an R6 limb is a single 2-stud block. A human 2-segment limb (thigh + shin, upper arm +
  forearm) forced onto it reads wrong, even when the geometry is matched exactly.
- R6 needs exaggeration vs human motion - but the hand-measured exaggeration below did NOT win votes.
- Finished, native R6 animations made by Roblox animators are the quality bar (Creator Store pack 125909948357929
  got "WOW AMAZING"); human mocap or other-engine clips folded to R6 were "all bad".
- Never hand-pose finals; never tune against a critic / taste model; show the owner, let the owner pick.

## The current numbers (owner absolute scores, 1 horrible .. 5 love)
| version | pairwise vs others | mean score | n |
|---|---|---|---|
| plain B (fold + pose-language kNN) | 68 W / 72 T / 5 L | 1.97 | 76 |
| B + measured style (amp / offsets / retime / foot lock) | 24 W / 11 T / 33 L | - | - |
| M (motion matching of whole loved pieces) | 0 W / 11 T / 57 L | - | - |
| B + one style factor (lean / speed / legs / torso / arms, half or full) | 0 W, all ties, 1 L | 1.7-2.1 | 6-8 each |
| fold ablation (limb aim, torso source, crouch) | legs 0.5: 2 W; arms 0.5: 1 W; rest ties | 2-3 | 1-2 each (too few) |
B is the best we have and it is still "bad" (~2/5). Anything that ships must clear 4/5.

## What failed, and why (measured)
1. Literal fold (first Kimodo fold): arms stuck out sideways. Cause: the R6 limb pivots off its long axis (C1
   offset leans pivot->end 18 deg arms / 14 deg legs); aiming -Y at the target pushed every limb out. Fixed:
   pivot-aware aim, twist from the elbow/knee bend plane; round trip 0.05 deg (diagnostics/fold_roundtrip.py).
   A perfectly straight limb carries no twist information at all - no fold can recover it.
2. Head pitched down: SOMA's rest neck->head line leans 17 deg forward; read literally it tilts every R6 head.
   Fixed with kimodo_fold.rest_pose (rest = bone offsets summed down the tree, measured from global_rot_mats).
3. SDEdit on the fold (medium_v3, t 30/50/70): drifts 0.6-1.1 studs from Kimodo, keeps the foot slide. Weakest.
4. Effector-guided sampling (reconstruction guidance on hand/foot FK): follows Kimodo best at w=10 (0.44 studs) but
   drags feet; at w=1 it is clean but arms drift out. Never rated as a winner.
5. Measured style profile (diagnostics/r6_style.py, r6_style.json): loved R6 vs Kimodo per joint/axis - torso
   twist 2-5x, leg swing 1.6-2.4x, strikes 2-3x faster, arm carry +-40-70 deg. Applying it (even one factor at half
   strength) never beat plain B. The AMOUNT of exaggeration is not the problem.
6. Motion matching (diagnostics/route_m.py): one whole loved piece per Kimodo beat, impact-aligned, inertialized
   joins. Lost every vote. Pieces from different clips never share a stance; joins up to 87 deg; the vocabulary's
   "loved combat" holds emotes and victim clips; the foot lock then has to drag feet 1+ studs.
7. Fold geometry tweaks (limb aim toward the upper segment, torso from pelvis/chest, crouch by spread or lean):
   mostly ties. Hand-tuning the mapping is not converging.

## Things that bit (process)
- look_r6 ignores --every: it renders every 60 fps frame. Gifs must take every 4th render at 66 ms (real time);
  earlier gifs played at quarter speed.
- Loved source clips are not clean: 53 of 589 loved combat pieces have their own one-frame snaps or held-frame
  hitches (35, 0, 38 deg steps) that any retime turns into pops. Filter sources by their own pops + hitches.
- Kimodo's motions face +Z; R6 faces -Z. Turn the first frame to face forward (kimodo_fold face_forward).
- A piecewise time warp with a rate step at the impact = a velocity step = a pop: ease the rate over ~8 frames.
- Pairwise page votes must come only from the page itself (Host / Origin / JSON checks: kit/anim/pairwise.py).
- A diagnostics script named like a kit module (motion_match.py) shadows it on sys.path: name scripts uniquely.

## The fixed test set (every candidate, the same 6)
muaythai, boxer, sword (_artifacts/kimodo/<name>.npz, prompts in diagnostics/kimodo_pipeline.py) +
run, idle, overhead (_artifacts/kimodo/test6/<name>.npz, prompts in diagnostics/translate_test.py).

## Promotion rule (owner)
A translator ships when its mean absolute score >= 4 across the 6 clips AND it beats plain B pairwise on >= 4 of 6.
Candidates that fail the hard gates on more than 2 of 6 clips are dropped before the owner sees them.

## Phase 2 - research translators on the 6 fixed clips (2026-10-13)
| translator | follows Kimodo (studs, B 0.45-1.01) | gate problems B does not have | mean deg from B | filter |
|---|---|---|---|---|
| T1 Motion2Motion (reimplemented: 21-frame patches of loved clips, alpha 0.85, 3 iterations) | 1.25-1.75 | boxer / sword / overhead floor | - | DROPPED (3 clips each) |
| T2 STyMo (vendored transformer, DTW-paired windows, NN gate) | 0.48-1.01 | boxer floor | 0-28 | to the owner (sword, idle not queued: under 2 deg from B) |
| T3 effector-conditioned medium_v3 (condition-consistency loss, condition guidance 3) | 1.04-1.41 | none - the only one clean on all 6 | 29-45 | to the owner |
Learned: a zero-initialised condition added to a trained diffusion model is IGNORED unless the loss forces it (v3:
given a real clip's own paths it reproduced them only 3% better than with none). The consistency loss on the
prediction's FK paths + a 10x lr for the condition layer + classifier-free guidance on the condition brought the
in-distribution path error from 0.537 (none) to 0.332. STyMo's gate shuts on motions unlike its few training sources
(idle: 0 deg change) - few-shot style needs sources that cover the test motion.

## Round 2 - native R6 (2026-10-13)
- GMR (R6 as an MJCF robot, whole-body IK, kit/anim/gmr_r6.py): all 6 test clips gate-clean, 0 pops, 0.75-1.06 studs from
  Kimodo's hands / feet - the best translation baseline so far by the gates.
- Kimodo-R6 (Kimodo-SOMA-RP fine-tuned on R6 natively, LoRA r16 + new projections, 20k steps, kit/anim/kimodo_r6.py):
  held-out loss 0.148 / 0.146 / 0.146 at steps 15k / 17.5k / 20k (plateau; the last is the best). It generates real
  motion (0 pops everywhere) BUT only for prompts phrased like its templated training texts: "boxer throws a jab and
  cross" -> 16 deg/s mean joint speed (a near-static guard); "A fighter quickly throws a combo of punches straight
  forward with the right hand ..." -> 209-299 deg/s. Guidance 6 only lifts the raw prompt to 56. The model is not
  underfit - its TEXT vocabulary is narrow. Rated this round with prompts rewritten in the training phrasing
  (_artifacts/kimodo_r6/style_prompts.json). Fix to try next: train on many natural phrasings per clip.
- The LLM2Vec text encoder: int8 on the GPU is accurate (cos 0.9965 vs the CPU) ONLY at batch 1 - padding in a batch
  moves the embedding to cos ~0.83. 1,441 texts: 6 min on the GPU vs ~5 h on the CPU.
- Checkpoints must all be kept (the first run overwrote one file; 2.5k-12.5k were lost - only their samples remained).
