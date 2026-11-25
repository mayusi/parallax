<!-- reference for the parallax-3d route card; verbatim from the skill page (2026-10-16) -->

## Stage 0 — Brief: what it is, how good, and how each part gets made
**Ask first.** `kit new asset <name>` writes `assets/models/<name>.brief.md`: ASK THE OWNER its questions before any
modelling (AskUserQuestion if your harness has it) — what it is, the END GOAL (master · game · showcase), the quality
and what "good" means to them, a QUALITY BAR (2-3 links / pictures of models at the level they want), the STYLE
(realistic PBR · stylised), the VIEW (first person · third person · world prop; how big on screen; which sides face
the camera), how much must WORK and the MOVING PARTS gameplay needs (only those), the EXTRAS it needs to work (a key
for its lock, the inside of a chest, a magazine), references, whose design it is (someone else's -> `private=True`),
and the HERO FEATURES: what players notice first, ranked, one line each with its ROUTE —
`1. wolf head | relief | the pommel's sculpted wolf | refs/side.png 410,120,470,170 | 30 mm`
(route: code · generated · relief · projected · procedural; the picture + its box + the size when a picture shows it).
Write their answers over each `<answer>`; every build warns `brief` until it is answered, reads it into
`facts.brief` (view, hero_features, quality_bar, style, moving_parts) and prints the hero features as a table
(`hero_features`: rank, route, picture, best px/mm). Too much and too little both waste the owner's time — the
brief is how you know which: the effort goes to the hero features, not to mechanisms nobody sees.
Hero / aaa builds warn `routes` for a hero feature with no route, or a sculpted / organic one built as `code`.
**The parts plan** (hero / aaa: `kit plan` asks for it) — under `- parts plan:` in the brief, every part you will
make, one numbered line each: `<part> | <shape modules> | <data> | <surface>` — its STACK from the table above,
e.g. `3. Slide | code: a.cad from the profiles + the draft as look-target | side + top traces, 2 models' sections,
186 mm (dims) | black nitride + scan, serrations, engraved marks, detail projection`. (The shape field names the
route words `kit plan` reads: code · generated · relief · projected · procedural — several where several are
used.) Deciding it here is what makes the pass ONE pass: no part starts with a stack that cannot reach the look, and
every part's data is gathered in stage 1 before it is needed.
**Declare the bar** in the script:
```python
a = rbx.Asset("marksman", ground=False, quality="aaa", ref_image="refs/marksman.png")
```
Tiers: **prop 55** (background props) · **hero 75** (anything players hold or look at) · **aaa 88** (showcase).
`lune run kit lessons 3d` · `lune run kit examples asset`. Get a REFERENCE image from the owner (or ask) and put it
in `refs/<name>.png`. Is there a template for the category? Use it.
