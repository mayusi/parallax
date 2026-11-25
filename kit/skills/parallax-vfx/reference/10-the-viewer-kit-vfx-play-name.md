<!-- reference for the parallax-vfx route card; verbatim from the skill page (2026-10-16) -->

## The viewer (`kit vfx play <name>`)
Impact frames in the viewer AND in a recording: the frames run on the HELD CLOCK — inside a hit-stop the world
stands still while the sequence plays through (frameTime = the preset time + the time elapsed in the hold,
deterministic by dt: a 60 fps record holds 0.18 s for 11 frames), and a frame shown during a hold is spent (no
replay when the world resumes). Record at 60 fps to see motion inside a frame (`--fps 60`); a true slow-motion
clip of a hit: the record page with `&slow=4&from=3.9&to=4.9&fps=60` (the clock steps 1/fps/slow, the video
stays 60 fps) — never slow a clip by repeating frames. Make every hit-stop as long as its frame sequence (the gate
`frames_in_hitstop`). `[` / `]` jump between the frames (paused on each), `H` holds every hit-stop 6x longer; a
held frame is composed once and blitted (no stutter). The server never exits
while it only serves; records and bakes run on another port (`--port 47812`) so the owner's viewer stays up.
Three panes. LEFT: the layer list by kind — M mutes, S solos, click selects; the inspector below shows the
selected layer's fields: `apply` = this page only, `save` = the field goes back to the preset or part FILE
(POST /preset) and the watcher reloads it. CENTRE: the viewport (drag orbit, wheel dolly, right-drag pan, R reset),
HUD, the booth picture-in-picture (B), a reference overlay (V), and a FREE CAM (`F` or the view menu: W A S D fly,
Q E down / up, shift fast, drag looks, wheel sets the speed; it starts from the current camera). RIGHT: Refs (the stills), Booth, Metrics (live
numbers, the brightness graph, the last recording's gate). TOP: variant switch (every variant is bundled beside
the base, same clock), view, speed, transport (space , . [ ] Home), loop (I O L), reset cam, `sheet` (a 4x4 contact
sheet of this view downloaded as PNG), record. BOTTOM: scrub + lanes (click select, double-click solo, shift-click
mute). Hot reload: saving the preset or a part on disk re-expands it through the kit and swaps it in, clock kept.
Click the viewport = which layers are drawn there (their emitter points projected, nearest first; click one to
select it); hover a layer row = peek (only that layer shows). `?` = the key help. `window.kitPlayer()` = the Player.
- `--kept <folder>`: the fracture plans, fields and point clouds a preset names are read from that folder's `fractures/`, `fields/`, `points/` instead of the effects folder's - for a made preset of the kit's own proofs played from build/ with `--animatic` (`kit/selftest/vfx/player/made.py`), never for a piece.
