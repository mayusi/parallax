<!-- reference for the parallax-vfx route card: a lens flare (2026-11-14; the VFX methods audit, stage 6) -->

## A lens flare that behaves like one (the lens layer's `"flare"`, `kit vfx flare`)

**The fault it answers.** The kit's "flare" was a star drawn into a texture and speed streaks: marks that sit still
on the screen. A real flare is the LENS answering a light: a glow where the light is, a long level streak through
it (the anamorphic lens), and GHOSTS strung on the straight line from the light through the middle of the picture,
which swing as the light or the camera moves. Roblox has no lens flare.

### On a lens layer
```json
{ "kind": "lens", "at": 0.2, "life": 1.4, "point": [0, 30, -80],
  "flare": { "strength": [[0, 0], [0.15, 1], [1, 0]], "ghosts": 5, "size": 0.18, "streak": 0.6, "squeeze": 1.6,
             "color": [255, 220, 170] } }
```
- `point` is the LIGHT (the layer's own point). Every frame the game and the player find where it falls on the
  screen and place the pictures from there; behind the camera nothing is drawn; as the light leaves the screen the
  flare fades, and is gone 15 % of the screen past the edge.
- `strength` (0-1 or a curve, MUST be said) · `ghosts` 0-8 · `size` the glow, as a share of the screen's height ·
  `streak` the level line's length in screen WIDTHS (0 = none) · `squeeze` 1-3, ghosts wider than tall (the
  anamorphic look) · `color` a colour or a sequence (the ghosts take theirs along it).
- Its three pictures are made once a project: `python kit/vfx/lens.py lens_glow lens_ghost lens_streak`, then
  `lune run kit vfx`. The validator refuses a flare without them (and they need an upload before a PUBLISHED game
  shows them: the owner's yes).

### `lune run kit vfx flare [--light 0.25,0.3] [--ghosts 5] [--size 0.18] [--streak 0.6] [--squeeze 1.6] [--color r,g,b]`
Draws where the marks fall for a light at that place of the screen (0,0 = top left) into `build/vfx/flare/look.png`
and checks them: the glow on the light, every ghost on the line through the light and the middle, ghosts on both
sides of the middle, nothing for a light off the screen. OPEN it. It makes nothing a preset reads, and it draws
simple shapes, not the three textures.

### Enforced
A beat that plans **Lens flare** needs a lens layer with a flare whose strength is above 0 and whose ghosts are
not set to 0 (or a texture drawn by `flares.py`); **Anamorphic effects** needs that flare with a `streak` above 0 (or a texture with `post.streaks`).
Speed streaks (`"streaks"`) no longer count as either.

### Limits, said plainly
- **HELD, in the browser player and in Roblox (2026-11-15):** the kit's own rules refuse a flare layer in this
  project, because its three pictures (`lens_glow`, `lens_ghost`, `lens_streak`) were never registered here:
  `python kit/vfx/lens.py lens_glow lens_ghost lens_streak` writes them, and `lune run kit vfx` registers them -
  that build stops while a piece is past its clock (2026-11-15: `flame_arc_v2`, which only the owner's words
  extend). In a game the three pictures must be uploaded too. Until then no flare can be drawn anywhere, and
  `kit/selftest/vfx/player/made.py` says HELD for it. The placement rule is ONE rule in three places (the game's
  code, the player's, `flare.py`), run against each other in 198 cases; where the pictures land on a real screen
  (the top bar's inset, a phone's notch) was never looked at.
- The gate wants a flare one can see: a strength that reaches 0.15 (and, for the anamorphic streak, a `streak` of
  0.2 or more). Whether it reads at that strength is the eye's.
- `"occlude": true` in the flare block hides the flare while something solid and seen stands between the camera
  and the light (one ray a frame; it is cut, not faded; off unless said). In the GAME only - the player has no
  place to stand a wall in - and NOT RUN in Roblox: what would show it is a wall moved between the camera and the
  light in the scratch place, once the flare's pictures are registered.
- The flare's three pictures are 512 px where the other lens pictures are 1024: a glow, a ring and a line with no
  fine detail, drawn over a fifth of the screen - kept at 512 on purpose (a quarter of the memory).
- Roblox draws the pictures alpha-blended, not added: over a bright sky the flare is weaker than a film's.
- One light a layer. No bloom of its own (pair it with the `world` layer's bloom). No anamorphic BLUR.
