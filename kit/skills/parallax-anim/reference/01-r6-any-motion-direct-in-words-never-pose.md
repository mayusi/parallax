<!-- reference for the parallax-anim route card; verbatim from the skill page (2026-10-16) -->

## R6 — ANY motion: DIRECT in words, never pose (the owner's route since 2026-10-12)
Every hand-posed or rule-built R6 move was rejected ("3/10", "horrible"); every human-made native R6 clip the owner
saw was fine or loved. So on R6 the model DIRECTS and real human motion PERFORMS — no joint angle is ever typed:
1. `lune run kit anim library` — once per library growth: every native R6 clip measured on the rig and described in
   words (hand, strike direction + speed, two-handed, legs up, lunges, jumps, crouches, spins, holds, loops), tagged
   game-safe (Creator Store / free-use DevForum posts) or study-only, cut into PIECES (windup / strike / recover /
   hold / move / cycle), and the human-vs-machine critic retrained. The owner rates clips at
   http://localhost:8765/find (`.claude/launch.json` "r6-picker") — every rating counts at once (the flywheel).
2. `lune run kit anim find "<words>"` — whole clips, loved first (`--take strike` = pieces). If one already does the
   job: `python kit/anim/motion_lib.py adapt <id> --as <Name> [--mirror --tempo 1.2 --hitstop 4 --trim a:b] --render`.
3. Nothing fits → write a SCRIPT of worded steps and `lune run kit anim compose <script.json> --render`:
   `{"name": "OverheadChop", "steps": [{"say": "two handed sword overhead", "take": "windup"}, {"take": "strike"},
   {"take": "recover"}, {"say": "sword idle stance", "take": "cycle", "seconds": 0.8}]}` — a step without "say"
   CONTINUES the same clip (real transitions beat blends); joins are chosen by pose distance, each piece is turned to
   face where the last ended, the learned R6 arm slides polish it. kit/anim/motion_vocab.py.
4. `lune run kit anim critic <clip.json>` — P(human-made), trained on human clips vs the owner-rejected machine moves
   + machine-ized copies (3-fold, families held out together: human 76%, machine-ized 89%, owner-rejected 76% of 72). Below 0.5 = rebuild it from
   pieces; never "fix" it by hand-posing.
5. Several characters: a CUTSCENE script (actors + beats: idle / act / strike with teleport, push, spin, launch,
   slam, hitstop / vanish / appear) → `lune run kit anim cutscene <script.json>` renders every actor as its own copy
   of the owner's rig (fidelity-gated), afterimages, flashes, impacts and a planned camera →
   `_artifacts/r6lib/cutscenes/<Name>/<Name>.mp4 + .gif + .blend`. Preview first: `python kit/anim/cutscene.py make
   <script> --every 24` (a contact sheet in ~30 s). Example: assets/animations/cutscenes/TeleportBeatdown.json.
6. Edit a human clip instead of authoring one: a `<Name>.warp.json` (`kit/anim/warp.py`: time_warp, amp_scale,
   additive, transplant, hold_mean / hold_from, delay, inherit_twist, sword) is built by `lune run kit anim <Name>`.
   **Fill between key poses (LOCOMOTION)**: the op `{"op": "fill", "keys": [frames], "group": "locomotion"}` keeps the
   keys and fills every gap by length - slerp under 30 frames, the R6 motion model (`_artifacts/r6model/medium_v3.pt`,
   kit/anim/motion_model.py) over 45, a crossfade between; 4 samples, the best by pops / foot jitter / DTW to loved.
   Measured on held-out locomotion: level with slerp at 20-frame gaps, better at 30+ (MOTION_MODEL_PLAN.md). NOT for
   combat yet: slerp beat it on held-out loved attacks (the op warns). No model file -> slerp, said in the log.
Licence: game-safe clips can ship in the owner's Roblox games (re-upload under the game's owner); study-only never.
