# __name__ — the brief

ASK THE OWNER these BEFORE modelling (AskUserQuestion if your harness has it, else ask in chat) and write their
answers over each `<answer>`. Doing too much wastes their time, doing too little wastes their trust — the brief is
how you know which. A hero / aaa build warns (`brief`) while an `<answer>` is left. Every build reads the answers
(the verdict's facts.brief and its hero_features table): keep the `- question: answer` form.

- what: <answer>  (what it is in the owner's words; the real object or design it is based on)
- end goal: <answer>  (master: the no-limits original · game: the Roblox version · showcase: renders / a turntable)
- quality: <answer>  (prop 55 · hero 75 · aaa 88 — and what "good" means to them: realistic, stylised, clean)
- quality bar: <answer>  (2-3 links / pictures of models at the level they want — what "good" looks like)
- style: <answer>  (realistic PBR · stylised)
- view: <answer>  (how players see it: first person · third person · world prop; how big on screen — a quarter of
  the screen, a hand's width, a few pixels across the map; which sides face the camera)
- function: <answer>  (static · the main parts move · everything works — name each moving part and what it does)
- moving parts: <answer>  (only the ones gameplay needs, each with what it does — or none: the rest stay still)
- extras: <answer>  (what it needs to WORK: a key for its lock, a magazine, a strap, the inside of a box)
- references: <answer>  (pictures / links the owner gives; more you may fetch — ask before downloading)
- ownership: <answer>  (the owner's own design, or someone else's: a game's weapon, a film prop -> private=True)
- hero features:  (what players notice first, most important first — one numbered line each:
  `<feature> | <route> | <what it is> | <picture> <x0,y0,x1,y1> | <size> mm` (the picture, its box in that
  picture's pixels and the feature's size when a picture shows it). ROUTE, how it gets made: code (shapes in the
  build script) · sculpt (a.sculpt: clay added, carved, blended, stroked and roughened in code — a head, a creature,
  roots, rock) · generated (kit gen) · relief (a picture's normals: kit vision relief) · projected (a picture or
  decal on the surface) · procedural (a material, a scan). Sculpted / organic forms — a head, a creature, foliage —
  are never `code`. Add a line per feature; the effort goes where this list says)
  1. <answer>

- parts plan:  (EVERY tier — `kit plan` holds the brief until it is written, and refuses a route the owner's
  verdicts rejected: kit/knowledge/vault/3d/routes.md — every part you will make, one numbered line each: its STACK of modules,
  `<part> | <shape modules> | <data> | <surface>`, e.g. `3. Slide | code: a.cad from the profiles + the draft as
  look-target | side + top traces, 2 models' sections, 186 mm (dims) | black nitride + scan, serrations, engraved
  marks`. The shape field names its route words (code · sculpt · generated · relief · projected · procedural — several when
  several are used). Pick each stack from the table on the parallax-3d skill's first page — this is what makes the work
  ONE planned pass: `lune run kit plan <name>` reads it. A part made in CODE also names its METHOD as the builder
  call(s): `code: a.box in a.repeat, a ring` · `code: a.sweep, tapering` · `code: a.box, a.loop + a.inset + a.push,
  a.round` — many alike are repeated or scattered (say how many: `Teeth x12`), long curved forms swept or bent,
  never typed one by one or left as boxes (reference/06, "Which method for which part"); the build is held to the
  calls and the count the line names)
- draft:  (stage 2 — the generated 3D draft you made: `kit gen views` / `kit gen` / `kit gen parts`, or `none: <why>`)
- reference models:  (stage 1 — the 3D reference models measured / inspected, or `none: <why>` when none exists)
