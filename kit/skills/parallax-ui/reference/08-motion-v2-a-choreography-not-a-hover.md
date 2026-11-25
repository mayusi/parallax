<!-- reference for the parallax-ui route card; verbatim from the skill page (2026-10-16) -->

## Motion (v2: a choreography, not a hover)
```json
"motion": { "enter": { "type": "swell", "delay": 0.5, "duration": 2.4, "ease": "sine" },
            "loop": { "type": "flicker", "speed": 0.8 }, "hover": "brighten", "press": "sink" }
```
- enter: `fade rise drop sweep pop bounce slam swell wipe typewriter` (a word takes the identity's `motion.enter`
  timing; `bounce` = from 60 % with an elastic overshoot, the simulator pop); ease: `quad sine back expo linear
  elastic`; `"stagger": 0.08` on a container spaces its children.
- loop: `pulse breathe blink spin sweep flicker glint float wobble` (`float` = a pet / egg / icon hovering 6 px,
  `wobble` = a NEW! tag rocking 6°); hover: `lift grow glow brighten`; press: `sink flash`.
- The strip (`--motion`) and the runtime play the SAME plan: delays + container stagger in sibling order.
- Reels (`<Screen>.reel.json`, `kit ui reel`): tracks key a node's props over time; several tracks on one node ADD
  their `dx` / `dy` (a shake on top of a slide), the last one does not win. Macros expand to tracks:
  `{"macro": "flipbook", "node": N, "frames": "<id>/<p>_{k}", "count": n, "from": t0, "to": t1}` (frames once),
  `{"macro": "cycle", ..., "fps": 12}` (looped all reel long: grain, flicker), `{"macro": "weave", "node": N, "amp": [2, 3],
  "fps": 12}` (film gate weave by whole pixels). A `text` track on a `number` node swaps its digit cells (as
  `Ui.number` does in game); `text_color` keys a label's colour. The critic (`<Screen>.critic.json`) checks the
  Material 3 timing rules: ease out to enter, in to leave, 0.15–0.6 s entrances, staggered siblings, a 3–8 %
  overshoot on the hero beat, a still moment to read.
