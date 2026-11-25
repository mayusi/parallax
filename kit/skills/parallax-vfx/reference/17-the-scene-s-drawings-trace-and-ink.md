<!-- reference for the parallax-vfx route card: stage 1 (trace) and stage 3 (ink); 2026-11-13, the VFX methods audit -->

## The scene's drawings: trace, then ink (the owner's method list: hand-drawn effects, frame by frame)

Why: an anime effect is DRAWN shapes - a flame with cut-outs, a crescent that thins from its tail - held two frames
at a time. The kit read a scene's colours and its timing; nothing carried the drawings themselves into the effect,
and its "drawn" sheets were simulations pushed through a posteriser (measured 2026-11-13: the FlameArc flame tongue
fills 2 % of its cell). Two commands carry the drawings; neither makes a look by itself.

### 1. `lune run kit vfx trace <set> [--beat N] [--tones 3] [--lit 0.6] [--box x0,y0,x1,y1] [--window a,b]`
After the breakdown and its dense read. The beat's main shot is read at the clip's own frame rate:
- **the cut-out** - what the dense read calls the effect (the set's hue band, coloured and lit, or white-hot; with no
  measured hue, what is brighter than the quiet picture). `--box` keeps a part of the frame (0..1 from the top left);
  `--lit 0.6` keeps only what is that bright: the floor and the walls an effect LIGHTS are in its hue band too.
- **the drawings** - consecutive frames that show one shape are ONE drawing, held. A drawing is taken from all its
  frames at once, so the clip's noise drops out. The summary says on ones / twos / threes.
- **the tones** - the effect's FLAT colours (read from flat patches inside the drawing, never the anti-aliased rim),
  darkest first, at most `--tones`; two tones that are one colour fold into one.
- **the curves** - per drawing and tone, every piece's outline and every hole in it (the cut-outs) as closed curves:
  the pixel staircase smoothed away, drawn points (a flame's tips) kept sharp, a round end kept round.
- **the check** - each drawing is drawn again from its curves and laid on its cut-out (`fit`); under 90 % is named.
  SAID, in the summary and on the picture: a drawing the frame's edge or the `--box` CUTS (`cut`: the share of its
  outline that is that straight edge; such an outline is not the drawing's).
  REFUSED, never traced: a cut-out over 60 % of the frame (a flash, a background), one that runs along 35 % of the
  frame's border, more than 48 pieces (speckle).
Writes `build/vfx/trace/<set>/beat<k>.json` (curves normalised to the frame, colours, holds: numbers, never a frame)
and `beat<k>_d<nn>.png` per drawing: the scene's frame, the trace laid on it (cyan = the silhouette, magenta = the
inner tones, a yellow ring on every sharp point), the trace alone. OPEN them. `--keep` also writes
`assets/effects/refs_measured/<set>.trace.beat<k>.json` - only after the owner's yes to keeping curves in the repo.
Any folder of frames: `python kit/vfx/shapetrace.py --frames <dir> --fps 24 --out <dir> [--hue lo,hi]`.

**What a real beat showed (the one probe, flame_arc_set beat 1, 2026-11-13; private, nothing kept):** the key beat
is a whole-screen composition, not a card. 22 drawings in 28 frames (mostly on ones), a quarter to 40 % of the
frame, 4,000-7,000 points and 300-450 sharp points a drawing. The trace carried the arc's white core and the black
gaps between the flame licks. Three things it also did, to know before using it:
1. the floor the fire lights is traced with the fire (`--lit 0.62` drops the dim part, the bright part stays);
2. the frame's edge cuts the arc, and the trace's shape is cut with it (the border rule did not refuse it at 35 %;
   the summary now says so, and how much of the outline is the cut);
3. the scene's saturated yellow came back paler (a tone is the MIDDLE colour of its pixels, and that band holds
   blown-out pixels too); the character's face, a small piece in the hue band, was traced as fire.
So: frame ONE element with `--box` (a cluster of licks, the arc's tip), not the beat; look at every picture.

Limits, said plainly: it reads colour and light (a dark effect is not seen); a camera that moves inside the shot
moves the drawings; a soft glow becomes the outermost tone; the rule that tells a drawn point from a tight round end
is a narrow one (two scales of one turn, kit/vfx/shapetrace.py `_corners`) and was set on made shapes.

**The camera (2026-11-13, `reference/21-*`):** the trace measures the shot's camera before it traces. A camera that moves is REFUSED without `--track`;
with it the frames are stabilised and the trace is of the window every frame covers (the trace's file says which: `"tracked"`).

### 2. `lune run kit vfx ink <key> --from <trace.json> [--drawings a-b] [--between 1] [--loop] [--cell 256] [--register beat|drawing] [--gray] [--line 2]`
The trace's drawings drawn again as a sprite sheet (stage 3, textures). It draws the CURVES at the cell's own size,
so an edge is as sharp in a 512 px cell as in the frame; it never scales a picture up.
- **a look first, a texture only from a KEPT trace** - from a trace in `build/` it makes the LOOK strip and says
  "A LOOK ONLY": no spec, no frames. A texture spec is written only from a kept trace
  (`assets/effects/refs_measured/`, `trace --keep`, after the owner's yes to keeping curves): a spec must be able to
  ink its sheet again, and `build/` is not in the repo.
- **the window** - `--register beat` (default): one square window round all the chosen drawings, as small as holds
  them: every drawing sits where the scene put it. `--register drawing`: each drawing centred, all at one scale (a
  card the preset moves itself). The summary says how much of its cell the largest drawing fills.
- **one cell a DRAWING**, never a frame: a drawing held two frames is one cell, and the flipbook's rate holds it.
  The summary gives the preset line: `"flipbook": {"layout": [cols, rows], "mode": "Loop", "fps": 12, "blend":
  false}` (on twos at 24 = 12 drawings a second). With blend on, the engine cross-fades two drawings into a ghost of
  both. With the mode left out (OneShot) the engine spreads the cells over the particle's life and the rate means
  nothing: a life of cells / fps seconds is then the same timing. The engine plays 30 cells a second at most; when
  that cuts the rate the summary says how much too slow it plays. A flipbook has ONE rate: drawings held 2, 2, 1, 3
  frames play evenly, and the summary says so.
- **a sheet is FULL** - the engine plays every cell of a sheet, so an empty cell is a blank frame: 1, 2, 4, 8, 16, 32
  or 64 cells. Choose `--drawings a-b`; with `--between` the count fills a sheet only when it loops (`--loop`: the
  last drawing's in-betweens lead back to the first).
- **in-betweens** (`--between N`, up to 3) - when two drawings are the same pieces (as many pieces, as many cut-outs
  in each) the in-between is made point to point: a sharp point meets a sharp point, every point moves its share of
  the way, the shape is grown to the area between its two drawings' (it neither swells nor shrinks). When they are
  NOT the same pieces, or the shape turns so far that it would collapse on a straight way, it is made from distance
  fields: that handles a piece splitting off and ROUNDS a drawn point (the summary counts those pairs); two such
  drawings that barely overlap are refused - a blend, not a drawing.
- **`--gray`** - the tones as greys, the lightest white: one sheet a preset tints. **`--line N`** - an ink line N px
  inside the silhouette's edge.
- **its checks** (a sheet that fails one writes NO spec and NO frames; an earlier sheet of that key stays as it
  was, and the summary says so): `fill` (the largest drawing covers 6 % of its cell or more; the 2026-11-13 flame
  tongue was 2 %), `empty`, `full`, `clear` (nothing reaches a cell's edge), `hard` (the edge is a pixel or two),
  `flat` (the inside is the trace's tones), `moves` (no two neighbouring cells the same), `volume`. A drawing the
  frame or the box cut is SAID again here.
Writes `build/fxlab/<key>/NNN.npy` + `assets/textures/<key>.json` (`"recipe": "ink"`, with the trace it came from
and its options) and `build/vfx/ink/<key>_strip.png`: every cell 320 px over a dark and a light ground, in-betweens
marked. OPEN it. Then `lune run kit vfx` packs, checks and registers the sheet like every other (fxfinish.py); a
sheet whose frames are gone, or whose trace was made again, is inked again by `kit vfx` from its spec.

**What a real beat showed (the one probe: a boxed part of flame_arc_set beat 1 inked into a scratch folder,
2026-11-13; no spec written, nothing kept):** eight drawings came out as eight cells that pass every check and are
still not a sheet to use - the box cuts the drawing along straight lines (said: all of them, up to 20 % of an
outline), and the floor the fire lights is in the cells. Choosing WHICH pieces of a frame are one element is not
built; until it is, trace a beat whose element stands alone in the frame (a spark, an ember, one lick).

Limits, said plainly: the sheet is as good as its trace; an in-between is geometry, not an animator's choice of a
breakdown drawing; the point-to-point pairing matches pieces by their nearest centres and has only been tried on
made shapes; `flat` accepts any mix of two tones, so a foreign colour that lies between two tones passes; nothing
here was checked in Roblox.
