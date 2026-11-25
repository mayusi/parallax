<!-- reference for the parallax-vfx route card: following the camera inside a shot (2026-11-13; the VFX methods audit, stage 7) -->

## Following the camera (`kit vfx track`)

**The fault it answers.** Every reading the kit takes off a scene compares a frame with the one before it: the
timing read (which frames are held), the trace (which frames are one drawing). When the CAMERA moves inside the
shot, every frame differs from the last and the reading says "everything changed on every frame": a pan reads as an
effect drawn on ones. On the made panning shot the made flame, drawn on twos, traced as 12 drawings of one frame
each; followed, as 6 drawings of two.

### `lune run kit vfx track <set> [--beat N] [--window a,b]`
It follows points of the BACKGROUND (everything that is not the effect's measured colour) from frame to frame, fits
the move they share - a shift, a zoom, a turn; the effect and whatever else moves on its own are outvoted - and
gives every frame's place in the FIRST frame's picture. Grain is smoothed away first: a camera that stands is not
read as one that trembles.
- A frame pair is FOLLOWED when 12 or more background points agree (half of all the points or more) to within a
  pixel; a shot is followed when 4 in 5 of its pairs are. A flat background, a cut or a flash "could not be
  followed": nothing is guessed, no move is invented.
- The camera STANDS when NO frame sits away from the first: no steady pan (under 0.055 % of the frame's width a
  frame), no frame further than 0.47 % of the width from where the first was, none larger or smaller by 1 %, none
  turned by 0.3 degrees. A shake that ends at rest, a pan there and back, a roll all MOVE. The limits are shares of
  the frame, so the trace (960 px) and the timing read (320 px) say the same of one shot.
- The points that agree must be spread over three of the frame's four quarters: one large thing that moves on its
  own in a corner is not the camera.
- Writes `build/vfx/track/<set>/beat<k>.json` (every frame's move; the pan, the drift, the zoom) and
  `beat<k>_track.png`: the first, middle and last frame as the clip has them (top) and stabilised (bottom), one grid
  of lines over all six, the window every frame covers boxed in yellow. OPEN it: on the bottom row the background
  sits under the same lines in all three.

### In the trace (this is where it is enforced)
`lune run kit vfx trace <set> --beat N` measures the camera itself, before it traces:
- the camera MOVES and `--track` was not given: REFUSED ("the camera pans 3.4 px a frame ... traced like this
  every frame would read as a new drawing"), and no trace is written;
- with `--track`: the frames are laid into the first frame's picture and cut to the window every frame covers; the
  trace is of those, its curves in the window's coordinates (`"tracked"` in the trace's file says which window);
- the camera stands: traced as it is, with or without `--track`;
- `--no-track`: the way out when what was followed is NOT the camera (a cloud of smoke filling the frame can be
  taken for it): the clip is traced as it is, and the trace's file says it was told to;
- `--box` stays a share of the FRAME: with `--track` it is carried into the window;
- the camera could not be followed: traced as it is - and when every drawing then lasts one frame, the summary says
  CAUTION: a moving camera reads exactly so. `--track` on such a shot is refused (nothing to stabilise by).

### Limits, said plainly
- It follows a FLAT picture: a shift, a zoom, a turn. A camera that travels through depth makes near things slide
  past far ones: the far background is followed and the near slides.
- An effect that fills most of the frame leaves too little background: "could not be followed".
- A clip an uploader cropped or reframed is followed as it is.
- The timing read (`denseclip.read`) stabilises a moving window by itself, on whole frames, and its note says so.
  The same read is used on the kit's OWN recordings: whether a recording's deliberate camera kick is then taken
  out, changing a comparison that was like for like, has not been checked.
- A large thing that is not the effect's colour and moves across most of the frame (smoke, rain) can still be taken
  for the camera when it is spread over the frame: `--no-track`.
- Tried on a made shot only: no real scene has been through it.
