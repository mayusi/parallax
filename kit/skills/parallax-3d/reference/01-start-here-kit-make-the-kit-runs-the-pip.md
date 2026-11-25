<!-- reference for the parallax-3d route card; verbatim from the skill page (2026-10-16) -->

## Start here: `kit make` (the kit runs the pipeline, not you)

```
lune run kit make <name> "<the object>" --tier prop|complex|hero [--private] [--photos | --concept] [--fresh]
```
ONE command makes the model, inside the owner's hard budget — **10 minutes for a prop, 30 complex, 60 a hero**. It
runs every stage below by itself: the object's category and graded sizes (its dossier if it has one); its VIEWS —
a real named object's photos (the dossier's turntable, else `refs find` + `refs rank`; a name with a number or a
weapon is "real"), a generic one's CONCEPT sheet (`vision concept --sheet views`: PHOTOREAL front, left side, back of
ONE design — found photos of "a wooden chair" are many chairs, a museum's black-and-white one among them); each cut
out and traced (a real photo is measured against, a concept only REGISTERED for painting — never measured); a much
sharper dossier photo of a view (the maker's 8124 px Glock side) projected instead of the rig's frame, its side
checked by its outline (a label can be wrong: that "side-right" photo was the LEFT side) and its colour matched to the
rig's; reference models found and GRADED (torn surfaces, floating debris, a raw scan's jagged surface, proportions —
`kit/blender/model_quality.py`); base shapes from every generator the views allow (Hunyuan multi-view, Pixal3D,
TRELLIS.2 single, PartCrafter parts — a later one only if the paint and build still fit after it, each stopped at the
time left) and, from a real object's own traced side + front photos, its visual hull twice: boolean (make_hull: crisp)
and SCULPTED (make_sculpt_hull: always closed, edges rounded 1.2% of its length); every candidate CLEANED (welded, specks dropped, holes filled, faces outward, at most 300k faces; a hard
surface also denoised with its edges kept and its flat faces made flat: `rbx_denoise`) before a TOURNAMENT that
renders each from the views and scores outline, look and proportions (crispness is reported, never scored: it once
picked a crisp but warped Glock); the winner fitted per axis to graded sizes (`import_mesh(stretch=True)`), painted
(Hunyuan Paint — a painted mesh that comes back torn, over 5% open edges, is refused), given one finish by what it is
made of (`rough=`, `scan=`: the generator's metal / roughness guesses replaced) and a LIFE read off its words (`life=`:
"an old chest" heavy, "a new chair" new, else light — dirt in its crevices, worn edges: never factory-fresh), and its
views PROJECTED onto it with
their fine structure as relief (`a.project(..., relief=)`), one side view mirrored to the other; the build, the render
beside the views, and for a hero the judge packet.
Every module ends RAN or SKIPPED with a reason the code checked — the report (`build/make/<name>/report.md`) fails
on one that did neither.
- When a generated model looks WRONG (see-through, a pencil sketch, black cracks), measure its mesh before blaming
  textures: welded, a closed triangle mesh has about half as many vertices as faces and ~0 open edges
  (`make.glb_topology`). A flat-shaded glTF is a triangle soup; decimated as one, it shreds.
- A **hand-written hero / aaa build builds at its tier and must pass EVERY hero check, no waiver** (`rbx.Asset`;
  the owner, 2026-11-11, kit card 38a9: it replaced the 2026-10-09 refusal of every hero kit make did not make, and
  the KIT_HAND_BUILD switch): a judgement it declares off (`see_through=True`, `through=True`, `stage_gate=False`)
  fails it. A script with no `quality=` builds at its BRIEF's tier (`- quality: hero` in `<name>.brief.md`). His
  7+ / keep pieces whose script is unchanged since he judged it build as before (`board/grandfathered.json`, by
  sha1). A made model's hand fixes still go in `assets/models/<name>.override.py`, run on top of the made model with
  `a` and `rbx` in scope — never instead of it.
- After it: LOOK at `build/make/<name>/compare.png` beside the photo; a hero's judges get
  `build/judge/<name>/PROMPT.md`. A candidate made before from the same photos is reused (`--fresh` remakes it).
- The stages below are what it runs, and what an override reaches for.
