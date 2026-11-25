<!-- reference for the parallax-vfx route card: stage 1 (breakdown --dense) and stage 5 (play -> dailies); 2026-11-12 -->

## The scene's timing, and dailies beside it (VFX studio-route plan, V0)

Why: a breakdown samples its clip at 2 frames a second, and a contact sheet shows frames 340 px wide. Anime effects
are timed frame by frame, so the scene's MOTION was never read: a session typed the timing from thumbnails. Two
commands close that; both read the clip (or our recording) at its FULL frame rate.

### 1. `lune run kit vfx breakdown <set> --dense [--beat <#>] [--scene-window a,b]`
After the breakdown (it needs the cuts). Per beat, every shot the beat covers is read on its own:
- **arrives** - frames from the first light until MOST (70 %) of the beat's light is on screen. "In one frame" = it
  snaps in. The frame it arrives on is the HIT.
- **stays** - how long it keeps most of its light. **goes** - from there down to a fifth.
- **freeze** - one drawing held longer than the rhythm itself holds one (a hit-stop). A 30 fps upload of a film on
  ones doubles every fourth frame: that is the upload's, and is not called a freeze.
- **drawn** - on ones / twos / threes, counted in 24ths of a second whatever the clip's frame rate.
- "at least" / "not seen" = a cut hid it (the shot opened on the effect, or ended while it was lit). Never guess it.

Writes `assets/effects/refs_measured/<set>.timing.md` (the table: read it beside the beat sheet) + `<set>.timing.json`,
and for each beat's MAIN shot (bold in the table: its light rises the most over its own floor) the frames round the
arrival: `build/vfx/breakdown/<set>_dense/beat<k>_<nn>.png` (two consecutive frames a picture, 640 px each) and
`beat<k>_page.png` (all of them + the light curve). The frames are private: `build/` only.
Time the chart's beats (`len`, `hold`) from this table, not from the 2 fps sheet.
The main shot is a rule, not a judgement: LOOK at the strips. If the wrong shot was taken, or a flash was read as a
cut, read the stretch you mean as one shot: `--beat <#> --scene-window <from>,<to>`.

### 2. `lune run kit vfx dailies <name> [--view hero] [--beat <#>] [--frames 12]`
`kit vfx play <name> --record` runs it by itself and ends its summary with `LOOK: build/vfx/dailies/<name>/`.
For every beat of the chart: the scene's main shot and OUR recording over that beat's stretch of our clock are read
the same way, the two hits laid on one moment, and
- `beat<k>_<nn>.png` - the scene's consecutive frames ABOVE ours at the same moments from the hit, two a picture.
  A reader's picture is shrunk past ~1500 px, so a whole page of frames arrives as thumbnails; these arrive at full
  size. OPEN THEM - every strip of the key beat at least. `HIT` is ringed, `HELD` marks a repeated drawing.
- `beat<k>_page.png` - the same frames on one page with both light curves over each other (for the owner's screen).
- the summary says what differs, in seconds: "it arrives: the scene in one frame, ours over 0.07 s", "it stays: the
  scene at least 0.73 s, ours 0.23 s", "a freeze while it stays: the scene none in the 0.67 s its shot shows, ours
  0.13 s (4 of its frames)", "the scene is drawn on twos, ours on ones". Each is one edit to the beat's timing; make
  it, play again, look again. What a cut hid is said as "at least" or left out, never compared as if it were seen.
An effect with no scene clip on this machine gets its own frames alone, as large (the summary says OURS ALONE).
The dailies fail only when ours never lights up (a blank recording).

### 3. `lune run kit vfx stylesheet <effect> [--view hero]` (V1)
Why: the owner approved the chart with ONE test frame, the key beat's. Every other beat's look was first seen in the
finished effect. The style sheet shows EVERY beat as a pair at the same size: the scene's main-shot frame at that
beat's peak, beside our recording's frame at OUR peak inside that beat's stretch of the clock. Under each frame: the
effect's five main colours with their shares and the key read (cover, white-hot share, colour bands, detail,
pieces). Under the pair: where ours falls short, by `kit vfx keyread`'s own rule, in plain words.
- `build/vfx/stylesheet/<effect>/beat<k>.png` - one pair a picture (two 768 px frames: read at full size). OPEN
  each. `build/vfx/stylesheet/<effect>.png` - the whole sheet, for the owner's screen and `kit review <effect>`.
- His yes: `lune run kit approve vfx <effect> "<his words>" --by owner --stage style` (or his click on the review
  page). It is recorded for TWO things: the sheet's ID (a hash of the preset's file, the set and the chart's plan:
  edit the preset and the id is another one) and the PICTURES he saw (`drawn`, a hash of the pair pictures as they
  are on disk). Record the same preset again (a texture or a mesh changed, the preset's file did not) and the sheet
  here is STALE: nothing to approve until it is drawn again; drawn again it has the same id and other pictures, and
  his word is asked again. Stricter than per beat, never looser. `--check` reads the pictures themselves every time.
- The CHART's picture works the same way: `kit vfx chart <set>` writes beside it what the picture shows
  (`build/vfx/charts/<set>.drawn.json`: its plan, the folder it was drawn from, whether it holds a test frame,
  whether its key beat was only guessed). The review page offers no approval of a chart whose picture is of an
  earlier plan (you edited the timing after drawing), of another folder's set of the same name, without a test
  frame of the key beat, or with a guessed key beat: draw it again first (the drawing keeps your timing; pass
  `--test <mp4@seconds>` for the test frame). A picture drawn before 2026-11-12 has no such record: draw it again
  before showing him. His yes: `lune run kit vfx chart <set> --approve "<his words>" --by owner`, or his click.
- A sheet with a beat where ours never lights up, or with no shot of the scene beside a beat, is refused: there is
  nothing true to show him. Falling short of the scene is NOT a refusal: it is what the sheet is for.
- The read counts everything in the set's colour band - lit skin and scenery too (FlameArc's ignition beat is a
  face lit by fire: "covers 79 % of the frame"). A SHORT line says where to look; it is no verdict.

### 4. `lune run kit vfx animatic <set> [--view hero]` (V2) - the motion, before the look is built

**Solid beats (2026-11-15; the owner's limitations file, F-R07).** A flat card facing one camera cannot say where
the effect STANDS, how deep it is, what it hides or whether it touches the ground, and from any other angle it is
a line. A chart's beat may say a solid instead:
```json
{ "beat": "strike", "t": 0.2, "len": 0.6, "solid": { "form": "pillar", "size": 14, "at": [0, 0], "lift": 0 } }
```
`form`: `ball` (a sphere `size` across), `pillar` (`size` tall, a quarter of that across), `slab` (`size` across, an
eighth thick, lying down); `at`: where it stands on the ground from the effect's place; `lift`: how far its
underside is over the ground (0 = it touches). Such a beat is a real 3D shape in the effect's own place at the
chart's timing, and `--angles combat,cine` (camera views of `kit/vfx/views.json`; `combat` unless said) works out
from each angle, by geometry: how much of it is in the picture, how much of the picture it covers, what hides it,
whether it is on the ground, what it touches (a pillar is tested as the upright cylinder it is drawn as). A solid
beat an angle cannot show (most of it outside the picture while it covers under 0.05 of it, a speck, over 0.8 of
it hidden behind another solid, the camera inside it) STOPS the run, saying which beat, which angle and what would do.
The record (`<set>.plan.json`, `angles`) keeps what every angle sees; the preset lists the angles as its views.
- A chart with no solid beat is the plan it always was: the same id, the same record, his yes still stands.
- A chart that gains a solid beat is ANOTHER plan (its id covers the solids and the angles): his word again.
- **The solids are DRAWN, with volume, from every angle** (stage 38). The player's film shows a solid as flat
  glowing colour laid over the others (a ball films as a disc, a nearer solid adds to a farther one) - so the kit
  draws them itself, by the rays its checks use: lit by where a surface faces, the nearer hiding the farther (in
  Roblox they are opaque), the ground dark under what touches it. `build/vfx/animatic/<set>_blocking.png` is every
  solid beat from every angle at the middle of its beat; `<set>_angles.mp4` is all angles at once on the chart's
  clock. Both are part of what the owner is shown. `lune run kit vfx animatic <set> --blocking [--angles ...]` makes
  just these, with no recording and no browser, under names of their own (`_blocking_look.png`, `_angles_look.mp4`):
  a look from other angles never changes the files his yes covers.
- **A solid may MOVE: `"to": [x, z]`** - where it has gone by the end of its beat (a wave that runs out, a
  projectile), evenly and straight. A chart with a moving solid is checked for FLOW: every solid is looked at at
  eleven moments of its beat from every angle, each other solid where IT is at that moment; the record's `angles`
  keep, per solid and angle, how far it goes, where its middle is in the picture at its start and its end (which
  way it crosses the frame) and what it touches on the way. One that an angle loses at one of those moments stops
  the run, saying at which; what happens between two looks (under a tenth of the beat) is not seen. In the player
  its way is done on the last drawing that is shown.
- Still not there: contact is with the flat ground and with other solids - not with a caster, a target or the
  scene's own set; a flat card of another beat in front of the camera is not counted as hiding a solid; the drift
  check of a BUILT effect against its animatic still reads light alone (its shapes and flow from the other angles
  are not measured back from a recording: that needs the player filming those angles).
- Limits: three plain upright forms on ONE flat ground; nothing of the scene's own set to hide behind or stand on.
  The id covers every angle's name AND where its camera stands: a camera moved in `views.json` is another plan.
  Two solids are "at the same moment" only when their beats start together (a beat ends where the next starts).
  `--blocking` was run through the real command on the kit's made project (a pillar and a ball that runs across).
  The WHOLE command with solid beats was run through the real player, hands-free, on a made set
  (`python kit/selftest/vfx/animatic/whole.py`, 2026-11-15, 33 s: a standing pillar on the hit and a ball that runs
  across, planned, checked from three angles, recorded by a headless browser, read back against its plan, with the
  side-by-side video, the beat pages, the solids' sheet and film; in the recording the pillar stands on the hit and
  the ball crosses the ground). It is not in the self-test table: it needs a browser. Not played in Roblox. The kit's `side` and `player` views frame a far target, not the effect's own place: a solid at the origin
  is outside them, and the run says so.
Why: the chart is approved as a still picture; the motion was first seen when the whole effect existed. The timing
animatic is the effect's MOTION in flat shapes, made by itself from the chart and the scene's read in about a
minute, with no textures and no sims:
- per beat ONE flat shape facing the camera - a disc, ring, arc, bar or wall, read from the beat's words ("arc",
  "ribbon", "shock wave" ...), else a wall when the scene's beat fills the frame, else a disc - at the chart's time
  and length, covering the share of the frame the scene's beat covers, arriving and going as the scene's main shot
  does, drawn on the scene's rhythm (on ones / twos), with the chart's hit-stops and slow motion. The key beat is
  white-hot, the others the middle of the set's measured colour band.
- a shape drawn on a rhythm changes only ON a drawing, so the plan's arrival and going are WHOLE drawings ("its
  light takes 0.150 s to arrive: drawn on ones that is 3 drawing(s), 0.125 s" is a note). The hit is a drawing that
  is there, and the chart's hit-stop freezes ON it. Its light is WHOLE on the hit drawing and at most 0.45 before
  it: the read calls a beat arrived at 0.7 of the way from its stretch's floor to its peak, and a beat's own
  lead-in can be taken for that floor, so the line sits anywhere from 0.70 to about 0.85 of the whole light.
- every number the plan settles itself is a NOTE on its beat (a beat cut short by the next one, a hold over the
  player's 1.8 s, a beat too short for its rhythm, a `slow` under 1, a value that is not a number). A beat with no
  room before the chart's end is an error: nothing is made.
- its preset is checked by the kit's own preset rules before anything is recorded (`kit/vfx/validate_preset.luau`).
- it is recorded in the player (`kit vfx play <set> --animatic` shows it by hand) and READ BACK: each beat's light
  must arrive in the very frame that first shows its hit drawing and cover what the plan says, or it
  is not an animatic he can approve, and the summary says which beat. A beat whose light is not its own is NOT READ
  and its notes say so - under three frames before the next beat, a hit that shows only after the next beat has
  started, another beat's shape still lit when it hits, or a stretch that opens on light as strong as its own. The
  summary says how many were read; the video shows the others; `--drift` cannot hold an effect to them.
- `--no-record` reads the recording that is already there - only when it IS this plan's
  (`build/vfx/animatic/<set>.recorded.json`, written when it was recorded, names the plan, the view and the very
  file). Re-time the chart and that recording is refused: record again. A run that is refused touches nothing of
  the animatic that is here - its record, its video, its preset; it stays his, and reads out of date when the
  chart is another one. A run that records puts its preset in place first: the animatic that was here reads out of
  date as soon as its preset or its recording is another one.
- `build/vfx/animatic/<set>_side.mp4`: the scene | the animatic IN MOTION, beat after beat, each pair laid on its
  hit, both light curves under them with a cursor; then the animatic alone at its own speed over a bar of its beats.
  WATCH it. `build/vfx/dailies/<set>_animatic/beat<k>_page.png`: the same as frames (the scene above the animatic)
  with what differs in seconds - where the CHART's plan is not the scene's timing, it is said there ("it stays: the
  scene at least 0.73 s, ours 0.40 s" = the chart gives the beat 0.4 s).
- where the scene could not say (its shot opens on the light, or ends while it is lit) the plan carries a NOTE and
  a plain default: read the notes in `build/vfx/animatic/<set>.plan.json` before showing him.
- His yes: `lune run kit approve vfx <set> "<his words>" --by owner --stage animatic`, or his click on the review
  page (`kit review <set> --lane vfx` works before any effect exists: the chart and the animatic). It is recorded
  for the plan's id and for the video and pages he looked at (and the WHOLE record beside them - its beats, its
  clock, its frame rate: change anything in it and it is no longer the animatic he saw). The id is of the chart's
  timing AND of where the scene's numbers came from (each
  beat's window of the scene, the clip, its cuts), the set's colour band and where the view's camera stands: a chart
  re-timed or pointed at another part of the scene makes the animatic out of date; so does recording it again.
- AFTER the effect is built: `lune run kit vfx animatic <set> --drift <effect>` reads the effect's recording against
  the animatic, each on its own clock. What it names (and fails on):
  - a beat whose light ARRIVES - is first at most (0.7) of what its stretch reaches - more than ONE drawing from
    where the animatic's does. One drawing and a quarter frame, nothing more. "At least" when it is still rising
    as the beat ends;
  - a beat whose light was already there before the beat started (it came early);
  - a beat with "no light of its own": what is lit when it starts has been on since the beat before (the beat
    before never goes out, or this one comes early by the whole gap: by light alone the two look the same).
  A beat on time but under half its planned size is SAID, not failed: the look is the style sheet's to judge.
  It answers only when there is something true to hold the effect against: the animatic here is current, the effect
  is built from THIS set, its recording is not older than its preset. It says whose motion it is: "its approved
  motion" only when `board/locks.json` holds the owner's yes for this very animatic, else "its animatic (which the
  owner has not approved yet)". A beat the ANIMATIC itself could not read back is listed as not held, with why.
  WHAT IT IS NOT: it reads light, nothing else. A flash at most of a beat's light on time, with the beat's body
  later, reads on time. It is a guard against layers placed late or early, not a judge of the motion: the dailies'
  frames are, and the owner.

### A recording is real time (2026-11-12)
The chart's times are the EFFECT's clock. The player's clock stands still through every hit-stop and runs slow
through a timewarp, and a recording runs on meanwhile. `denseclip.clock_of(preset, fps)` is the recorder's own loop,
frame by frame (held in the tests to the times two real recordings posted: the FlameArc animatic's 107 frames, and
starblade's 569 with slow motion and hit-stops of 1.5 and 0.9 s): one step of 1/fps a frame, the frame taken AFTER
the step; a hit-stop is the frame that stops on it plus the whole frames of its hold (0.12 s at 30 a second: three
held frames). So frame 0 shows 1/30 s, a moment is seen in the first frame whose clock has reached it, and a beat
the chart puts at 1.90 s, after hit-stops of 0.12 and 0.06 s, starts four frames later in its recording than on the
chart. A stretch ends two frames before the next beat (the next beat's first light was found in the last one).
The clock is that of the preset AS PLAYED: `kit vfx play` writes the bundle it gives the player (the `play` folder
beside the recording's booth, `<run>.json`: the preset expanded - beats' names resolved, parts' and variants'
hit-stops in) just before it records, and `denseclip.played()` reads it when it IS that recording's (written before
it, within the recorder's time limit: a bundle of the same name from another day is not). A preset that is not
composed (no `use`, `beats`, `variants`, `overlay`) is read from its own file. A preset's FILE can say something
else: starblade's has a hit-stop "at":
"blast" - read from the file the clock crashed, and the dailies of every recorded play of such an effect with it.
When the played preset is not surely known, the dailies, the style sheet and `--drift` say CAUTION.
Limits: an impact frame inside a hit-stop's `span` is DRAWN during the held frames, so a beat that is only such a
frame shows up to the hold's length before this clock has it. The read's floor is one rule for every recording: a
beat's own short lead-in can be taken for it ("arrives in one frame" of a shape that grew for two frames). And
these tools read the project's own `build/`: with a game active the play command records into that game's build
folder, which they do not see.

### What it cannot see
It reads LIGHT and the set's measured hue band (the key read's idea of "the effect"): a dark effect (black smoke,
ink) covers nothing; a moving camera counts as change ("lit and changing on every frame" is said, not hidden);
skin or scenery in the band is taken off as the shot's floor. The numbers say WHEN; how it LOOKS is what the
frames are for. A match on timing is never a verdict on the look: only the owner's is.

First read (flame_arc_v2, 2026-11-12): the scene's fire arc is there in ONE frame and stays for the rest of its
shot (0.73 s or more), drawn on ones, no freeze; ours grew over two frames, froze four, and was gone in a third of a
second. None of that was visible on the 2 fps sheet.
