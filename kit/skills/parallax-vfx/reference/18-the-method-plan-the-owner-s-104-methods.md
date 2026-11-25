<!-- reference for the parallax-vfx route card: the owner's 104 VFX methods and the method plan (2026-11-13) -->

## The method plan: the owner's 104 methods, enforced in use

The owner, 2026-11-13: "every method i mentioned for each pipeline keep going up until they are all mastered and
implmented into each pipeline and enforced in the terms of being used". His VFX list (104 methods, his words, his
order) is the kit's register, `kit/vfx/methods.json`. Each method says: whether the kit HAS it, has it PARTLY, is
MISSING, or Roblox has NO PLACE for it (then its stand-in); how the kit does it; its tool; and its **proof** - what
in a preset shows the method is USED (a layer kind, a key on that layer, the recipe of a texture it names).

### The commands
- `lune run kit vfx methods` - the whole list with each method's state.
- `lune run kit vfx methods <words>` - one method: how, its tool, what proves it ("drawn flame", "dissolve", "trail").
- `lune run kit vfx methods --set <set>` - a scene's plan beat by beat: what is planned, which methods each beat's
  own words call for (its row of the beat sheet), and every point still open.
- `lune run kit vfx methods --set <set> --beat N --use id,id [--not id="<why>"] [--drop id]` - write one beat's plan
  into `refs_measured/<set>.chart.json` (`"methods": [...]`, `"not": {id: why}` on the beat's row; the timing the
  owner approved is not touched).

### Where it sits on the route
After the beat chart's timing, BEFORE the chart is shown to the owner (stage 2a). `kit vfx chart <set>` draws the
plan under every beat in his words - green "made with: ...", red "NOT <method>: <reason>" - and warns while the
plan has open points. His approval keeps the plan he saw (`approved.methods`); a chart that carries a plan is
approved only from a picture that shows that plan (draw it again after any change to the plan).

### The gate (`kit vfx`, on every preset built from a scene; `kit vfx expand <name> --check` runs it on one)
It reads the preset AS IT PLAYS - expanded, and once more for each variant: a layer the preset or a variant mutes is
gone, a part's layers are in (they take the beat of their use: `"use": [{"part": ..., "beat": 1}]`). A layer that
draws nothing (fully transparent all its life, no size, no life) proves nothing, and neither does a key that does
nothing (`"uvScroll": [0, 0]`). A piece is refused when:
1. a layer names a beat the chart does not have, or no layer builds any beat of the chart;
2. a beat it builds names no method, or names one the kit has not built, or one Roblox has no place for (the
   message names the stand-in);
3. a planned method is not USED: nothing that plays in THAT beat meets its proof (a scrolling ring on beat 0 does not
   prove beat 1's "UV scrolling"; a sheet named like an inked one whose spec is an import does not prove
   "hand-drawn");
4. the beat's words (what is ON SCREEN and its shape, in the beat sheet) carry the cue of an ASK method and the plan
   neither uses it nor leaves it out with a reason. Today the one ASK method is **Hand-drawn effects animation**
   (cues: flame, flaming, fire, fireball, slash, crescent, smoke, smoky, puff, lick, wisp, tongue; "no flame" and
   "the fire gone" are no cue): an effect the scene DRAWS is made from the scene's drawings (`kit vfx trace`, then
   `kit vfx ink`), or the chart tells the owner why not;
5. a reason for leaving an ASK method out is not, word for word, on the chart the OWNER approved - an approval
   recorded by anyone else (`"by": "model-proposed"`) holds no plan, and a reason rewritten after his yes is another
   reason;
6. a method that was on the chart he approved is gone from the plan.
More methods than the plan are always free. A method whose proof is empty can be said and is not measured (the
gate's record lists it under "said"). Pieces that existed on 2026-11-13 are exempt by their folder and name
(`kit/vfx/scene_gate.json` "methods", frozen: adding one is loosening the gate). The owner may waive it for one
piece: `kit approve vfx <name> "<their words>" --by owner --waive methods`. `kit vfx chart <set> --replan` makes the
timing again and keeps every beat's method plan.

### Rules for whoever edits the register
- A method moves to HAS / PARTLY only in the commit that builds it, with its proof.
- Never change a proof to let a preset through; a proof may only name what the runtime reads
  (`kit/test/python/test_vfx_methods.py` holds the register to the validator's layer kinds and mesh keys, and to
  the owner's list word for word).
- A new ASK method needs a cue list that fits beat sheets as they are written, and a tool that is the scene's way.

Limits, said plainly: the gate reads what a preset is MADE OF, not how it looks - a planned method that is used
badly passes; cues are whole words of the beat sheet, so a beat sheet that does not say "flame" asks for nothing; a
layer tagged with one beat and timed inside another is not caught (the gate reads the tag, not the clock); the plan a
chart's approval holds is a line in a file, as the approval's words are; several methods are proved by the same kind
of layer (an impact frame, a mesh), so naming them adds little.
