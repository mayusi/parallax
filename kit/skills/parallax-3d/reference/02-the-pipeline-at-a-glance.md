<!-- reference for the parallax-3d route card; verbatim from the skill page (2026-10-16) -->

## The pipeline at a glance

`lune run kit plan <name>` reads the asset's files and prints these stages — done, partly done or to do, what it
found, and the exact commands for the next one. Run it when you arrive, and after every stage. Everything the stages
gather lands in the asset's PACK (`lune run kit pack <name>`: `assets/models/<name>.pack.json`) and the build READS
it — `pk = a.pack()`: `pk.size(...)`, `pk.profile(...)`, `pk.colour(...)`, `pk.levels(...)`, `pk.draft()` — so
no number is typed from memory or copied by hand between tools.

| # | Stage | Done when (`kit plan` checks) | Commands (`lune run kit ...`) | In the build script | Local AI used |
|---|---|---|---|---|---|
| 0 | **Brief** | the owner's answers; hero features AND a parts plan: each part's stack | `new asset`, `lessons 3d`, `examples asset` | `rbx.Asset(quality=, stage=, private=)` | — |
| 1 | **Gather** every reference before any shape | a REAL object's DOSSIER approved by the owner (facts graded from their sources, pictures and models reviewed by two keys); traced pictures of every side players see; sizes with sources; 1-2+ reference models measured / inspected; >= 2 px/mm on each hero feature; colours measured — all in the pack | `dossier new / source / fact / part / tell / add / check / review / sheet / approve`, `pack <name> object / size / colours`, `refs expand / find / patent / rank / pick / dims / coverage / parts / colour`, `library find / get / inspect`, `refs measure`, `learn`, `trace`, `refs crop / profiles / views`, `vision cutout / upscale / albedo / light / angle / concept` | `refs/<name>.spec.json`; the pack | BiRefNet, SAM 2.1 / SAM 3, SigLIP 2 + DINOv2, Real-ESRGAN, Marigold-IID, DiffusionLight, Qwen-Image-Edit (look only), FLUX.2 (concept only) |
| 2 | **Model sheet** (a new complex / hero / aaa piece) | the sheet drawn with no problem — every hero feature has a picture box, a size and ≥ 2 px/mm — and the OWNER approved it as it is now | `sheet <name>`, `refs coverage <name>`, `approve 3d <name> "<words>" --by owner --stage sheet` | the brief's hero feature lines: `<feature> \| <route> \| <what> \| <picture> x0,y0,x1,y1 \| <size> mm` | — |
| 3 | **3D draft**: generate before you code | a generated draft (or the reason for none) LOOKED at beside the references | `gen views` (2-4 views), `gen <name>` (one picture), `gen parts`, `gen mv-shape` / `gen omni` (private), `vision similar / differ` | `a.import_mesh` | Pixal3D, TRELLIS.2, PartCrafter, Hunyuan3D-2mv / Omni |
| 4 | **Blockout** (the same pieces) | the big shapes in clay against the sheet, drawn from a shape round, and the OWNER approved the proportions; no detail or bake before it | `blockout <name>`, `asset <name> --geo`, `approve 3d <name> "<words>" --by owner --stage blockout` | primitives / plain extrusions, one `a.trace_match` per traced view | — |
| 5 | **Shape**: each part by its stack | every traced view at its bar, parts matched, every CAD part a clean solid, proportions fitted | `cad check [--look]`, `watch <name> --geo`, `asset <name> --geo`, `fit <name> --write` | `pk = a.pack()`, `a.cad` (+ `cad_parts`), `a.loft / carve / extrude / fuse / cut`, `a.import_mesh`, `a.param`, `a.trace_match(parts=)`, `a.section_match`, `a.learned_from`, `a.spec` | TEED (the lines check) |
| 6 | **Surface** | each part's finish from data; markings engraved at their measured place; colours and roughness pass | `materials --sheet`, `vision albedo / relief`, `refs colour`, `gen texture`, `gen paint` (private) | `a.material(finish / real / scan / pattern)`, `a.zone`, `a.text` + `a.cut`, `a.decal`, `a.project(detail=)`, `a.relief / a.displace`, `a.texture_from` | Marigold-IID, MoGe-2 + Depth Anything 3, TRELLIS.2 texture, Hunyuan3D-2 Paint |
| 7 | **Mechanism** | every moving part jointed; the take-apart comes clear down to the screws | `schematic` | `a.joint`, `a.internal`, `a.disassembly`, `a.anchor`, `a.clear_path` | — |
| 8 | **Look and judge** | a full build LOOKED at beside the photos; fresh judges; their one fix list done | `asset <name>`, `judge` / `judge --pair` / `judge --tally`, `fit camera` | `<name>.review.md`, `refs/<name>.regions.json` | SigLIP 2 + DINOv2 (the look report) |
| 9 | **Present** | the showcase rendered; the game version and upload only when the owner asks | `showcase`, `optimize`, `upload` | `stage="master"` | — |

**Time budget** for a hero real object with a take-apart (a pistol), on a test PC: the owner called the
Silverballer's 3 hours TOO LONG — aim for **2**: brief 5 min · gather 25 (+ ~45 once for a real object with no
dossier yet: compiled once, every later asset of it reuses it) · draft (the GPU, in the gaps) · shape 40 ·
surface 20 · mechanism 15 · look and judge 10 · present 5. A prop: 30 minutes. Say the budget up front, time each
stage (`kit pack <name> time <stage> <seconds>`) and report against it.

### Rules of the pass
1. **All the data first.** Stage 1 gathers every picture, size and reference model the parts need — a fact found
   mid-build costs a rebuild (the Silverballer's half-cock hammer, the Glock's 7%-short scan). Ask the owner ONCE, up
   front, for what only they can get (the design's own pictures, close-ups).
2. **Never trust one source — and never a model's memory.** A real object's facts live in its DOSSIER (`kit
   dossier`), each graded from its sources: A the maker / a patent office / the owner, B two independent sites agree,
   C one source, D disagreement. A number a model typed counts only once a script found it in the cited source
   (`--quote`, the page's own words) or two reviewers (one blind) confirmed it. Pictures and models are measured by
   script against the A/B facts (the Glock's 7%-short scan and the Gen4's 204 mm both show there) and reviewed by two
   keys; a wrong reference is withdrawn the moment it shows, and another one found.
3. **A 3D draft before shape code.** A few minutes of GPU per generator (TRELLIS.2 ~4, Pixal3D ~6.5) — each run
   with the card otherwise IDLE, one at a time (a second GPU job spills into shared memory and runs 4-20x slower):
   do the CPU work — sizes, reference models, the parts plan — meanwhile. The 3D look-target, a proportion check
   against the reference models, and the shape itself for sculpted / organic parts (the draft stage).
4. **Every part gets a STACK, never one module** — chosen in the brief's parts plan from the table below: its DATA
   (pictures of every side, a reference model's sections, a sourced size, learned bevels), its SHAPE (CAD, a loft
   from measured slices, a generated piece — often two together, with the draft as the look-target), its SURFACE (a
   measured finish, a scan, a pattern at the real pitch, engraving, projected detail) and its CHECKS. A gun made with
   CAD alone is a screwdriver on a nut: the CAD gives the exact shape, the rest gives the look.
5. **The kit matches proportions, not you:** a number the references should decide is `a.param()`, and `kit fit`
   moves it to the traced views (CMA-ES over --geo builds) — never nudged by hand build after build. Weigh each
   view by how far its picture is trusted (`--weights side=1,front=0.4`: a drawing 1, a photo about 0.7, a
   concept 0.4) and hold one view out (`--hold front`): a fit that leaves the unseen view worse is an OVERFIT,
   said, and `--write` writes nothing. Parts linked in `a.trace_match(..., parts={...})` are fitted too: where the
   guard, the grip, the pommel sit, not only the whole outline. And the OPENINGS a trace names (its holes: a
   trigger guard's window, the gap between a guard and the grip) are measured by themselves and fitted: one
   outline IoU barely moves when a window is closed (`facts.references[].openings`, warning `openings_<view>`
   when the model covers over half of them solid; a part traced `"<part>!"`, outlines only, is left out). And
   what no picture shows: `a.section_match(...)` (each slice's width, depth and roundness against the measured
   reference's) and `a.form_match(...)` (the surface against a real 3D model both ways: its depth and cavities)
   are terms of the fit too. The fit names every term before -> after (`terms_before` / `terms_after`). A PHOTO
   view can hold its RELIEF as well: `a.trace_match(..., depth=True)` compares the model's steps and recesses
   inside the outline with the photo's (MoGe-2 normals + Depth Anything 3, made once per trace by
   `kit/vision/depth_ref.py`, about 40 s; the model ray-cast from the same camera) - `facts.references[].depth`
   (corr, where the picture is recessed and the model is not), warning `depth_<view>` under 0.15, a fit term. A
   photo's depth is relative and soft: it reads steps, pins, serrations and panels, not millimetres.
6. **The fast loops:** a CAD part in seconds with `kit cad check <name> --only <Part>` (no Blender); the whole
   model's checks with `kit watch <name> --geo` (a persistent Blender, no bake: seconds on a light asset, 2-7 minutes
   on a CAD-heavy hero — so iterate CAD parts alone and run --geo at milestones); a full `kit asset` only at a stage's
   end. `kit fit` runs one --geo build per evaluation: on a slow hero fit only the few proportions that matter
   (`--only a,b --evals 24`). The vision models WARM: `lune run kit vision serve` in its own terminal (or in the
   background) keeps them loaded — every `kit vision` edges / cutout / mask / depth / similar / differ / view call and
   every cut-out and rank goes through it (the kit's python models; measured: 10 calls 99.8 s
   cold -> 13.8 s warm, outputs pixel-identical; a cut-out ~0.6 s instead of ~11 s); a generator or a big vision model
   frees its GPU memory first by itself. Generate in the background while you write CAD and gather sizes / reference
   models (CPU work); GPU work — traces, cut-outs, other generators — waits until it finishes.
7. **LOOK at the end of every stage** — the render beside its reference pictures (`build/renders/<name>.png`,
   `kit vision differ <render> <photo>`), never the score: the score counts parts, triangles and materials.
8. **Time-box every fight.** A part that fails twice the same way (a fillet OpenCASCADE refuses, a join that loses
   material) changes approach: a simpler profile, its own body, another module in the part's stack.
9. **Judge once, fix once** (the look-and-judge stage): fresh judges, one fix list, one round; another round only for what the look
   still shows wrong.

### Which stack for which part
Every part uses several modules — pick each part's stack here, adjust it to the part, write it in the parts plan.

| The part is ... | Data (gather) | Shape (draft, shape) | Surface (surface) | Checks |
|---|---|---|---|---|
| machined / moulded, sizes known (a slide, frame, barrel, receiver) | photos of every side + the part's close-up (`kit refs find`, `kit trace --part-box / --part-text`); 2 reference models (`kit library inspect`, `kit refs measure`); sourced sizes (`kit refs dims`); bevels (`kit learned show`) | `a.cad` from `kit refs profiles` + the models' sections (`smooth_profile`, `fillet_each`); `a.param` + `kit fit`; the generated draft beside it as the look-target | `rbx.finish(...)` + `scan=` at the measured colour (`kit vision albedo`); edge wear; engraved markings; `a.project(detail=1.0)` for fine structure | `part_match`, `section_match`, `ref_sizes`, `a.learned_from`, `lines` |
| wrapping round (a grip, a stock, a shroud) | a reference model's slices (`kit refs measure`: levels); front + back photos; its texture's real pitch (`kit refs dims`) | an a.cad loft `loft_sections(from_levels(...))`; sculpted: its part of the draft (`kit gen parts`) | `pattern=` at the real `pattern_mm` + `a.zone` for the textured panels; `scan=` | `section_match`, `part_match` |
| a standard small part (screw, pin, spring, nut) | ISO rows (`kit refs dims find "iso 4762 m3"`); where it sits: an exploded / patent drawing (`kit refs patent`) | `cad_parts`: `screw`, `pin`, `roll_pin`, `spring`, `nut`, `clearance` | `rbx.finish(...)` (blued, black oxide, stainless) | `fastener_seat`, `fastener_support` |
| sculpted / organic / ornate (a head, a creature, a carved stock, foliage) | the biggest, cleanest pictures; chart views cut out (`kit vision cutout`); other sides to LOOK at (`kit vision angle`); depth (`kit vision depth`) | `a.sculpt` (clay in code: blends, strokes, creases, relief — the traced views as its guide); `kit gen views` / `kit gen` / `kit gen parts` → `a.import_mesh(..., crop=)` → `s.add_part` to repair and re-sculpt it; or a code form + `kit vision relief` → `a.displace` / `a.relief` | its generated textures, or `kit gen texture` → `a.texture_from`; `scan=` | `trace_match` per view, the look beside the photos |
| a whole static prop with good views | the views, cut out | `kit gen views` → a master, the parts that move cut out or code-built | its generated textures / `kit gen texture`; scans | `trace_match` per view |
| a marking (maker, model, serial, a logo) | its place and size measured on a close-up (`kit refs crop`, `rbx_trace.px`) | `a.cut(part, a.text(..., "engraving", depth=...))`; a logo: trace its close-up (`kit trace`) and cut the outline in | a printed / painted mark: `a.decal` | `marking_placement` |
| the finish and colour of EVERY part | `kit vision albedo` + `kit refs colour` on the most neutrally lit picture; wear and roughness by role (`kit learned show`) | — | `rbx.finish(...)` / `rbx.real(...)`, `scan=`, `wear=` / `grime=`; a look no material imitates: `kit gen texture` → `a.texture_from` | `colour_match`, `roughness_variation`, `pbr_values` |
