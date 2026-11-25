---
kind: reference
area: vfx
date: 2026-10-16
source: "kit/vfx/facts.luau (+ the probes below), measured in Roblox Studio on the bench place"
links: ["[[vfx/index]]", "[[vfx/graveyard]]"]
---

# VFX engine facts — measured in Studio, not assumed

Every fact here was MEASURED in Roblox Studio (the bench place, Edit mode unless said) with its capture on disk
(`build/vfx/facts/facts/facts_NNN.png`, git-ignored; re-run `kit/vfx/facts.luau` through the capture server to
regenerate). A fact the browser player shows but Studio does not is a player bug, not a look. Add a fact only with its
measurement and capture.

## Transparency on meshes (2026-10-16) — the big one

| what | measured | verdict |
|---|---|---|
| EditableMesh **per-vertex alpha** (`AddColor(c, a)` / `SetColorAlpha`: VfxMesh `fadeIn` / `fadeOut` / `fadeSides` / `erode`) | a tube with alpha 1 -> 0 bottom to top reads 253 top to bottom on Neon (= the opaque control); SmoothPlastic 63 flat; also flat with a SurfaceAppearance (AlphaMode Transparency, no ColorMap) and at Transparency 0.01 (facts_001, facts_006, facts_007) | **IGNORED** by Studio's MeshPart renderer |
| EditableMesh **per-vertex RGB** (`AddColor(c, 1)`) | a quad white (bottom) -> black (top): Neon 253 -> 29, Plastic 87 -> 27 (facts_007) | **RENDERS**, but black still occludes: not a fade |
| `MeshPart.TextureID` alpha on an EditableMesh part (Neon / SmoothPlastic, Transparency 0 or 0.01) | a striped Neon backdrop behind the card: 0 % of the stripes visible through it vs 49-60 % beside it (facts_009) | **IGNORED**: the sheet's transparent ground draws |
| `TextureContent` alpha at Transparency 0.01 | 0 % through (facts_010) | **IGNORED** |
| **SurfaceAppearance** `ColorMap` + `AlphaMode = Transparency` on an EditableMesh part | 40.8 % of the stripes through vs 48.8 % beside (facts_010) | **WORKS** — the only alpha route on a mesh |
| SurfaceAppearance `AlphaMode = Overlay` + ColorMap | 0 % through | opaque |
| setting `SurfaceAppearance.ColorMap` / `ColorMapContent` from a game Script (Play mode, server) | "The current thread cannot write 'ColorMap' (lacking capability Plugin)" | **NOT at runtime** — AlphaMode, parenting and `MeshPart.TextureContent` are writable |

SurfaceAppearance follow-ups (same day, facts_011 / facts_012):

| what | measured | verdict |
|---|---|---|
| SA (ColorMap + AlphaMode Transparency) on Neon vs SmoothPlastic | alpha works on both (stripes through 49 % / 43 %), but the drawn texels are DARK: luma 34 / 32 | SA **kills the Neon glow** (it renders PBR) |
| + `EmissiveStrength` 5 alone | luma 32 | no glow without a mask |
| + `EmissiveMaskContent` = the same sheet, strength 1 / 5 / 20, tint | alpha still works (39-43 % through); the brightest texels p95 208 / 246 / 225 | **GLOW + ALPHA on a mesh** — the route |
| + part `Transparency` 0.5 | the card nearly vanishes (luma 18) | uniform transparency still multiplies |
| + vertex alpha (fadeOut 1) | top 47 % / bottom 50 % through: no gradient | vertex alpha stays ignored under an SA too |

| a SurfaceAppearance's maps on FIRST use (flame_arc_dance_keybeat, booth, 2026-10-16) | the arc drew pale and untextured ~1 s after its SA was made (the hero pass, run second, was fine); a Decal preload of the same id did NOT warm it | SA maps stream on their own: `VfxStage.preload` now builds a throwaway SA with the maps and preloads it (fixed: the next first frame was textured) |

So a glowing, alpha-textured mesh shell IS possible in the engine: a SurfaceAppearance with ColorMap + EmissiveMask
(the same sheet) + EmissiveStrength + AlphaMode Transparency, AUTHORED AHEAD (a script cannot set the maps) and
cloned onto the EditableMesh part; fades / erode must move to the texture (a dissolve sheet) or to the uniform
Transparency, never to vertex alpha.

Consequence for the kit: `VfxStage` mesh layers set `TextureID` + a uniform `Transparency`, so in the REAL engine
every textured mesh shell draws its whole texture square (transparent ground included) and its erode / fades do
nothing; the browser player (three.js) honours both, so player and booth disagree on every mesh layer. The route that
works: SurfaceAppearances with ColorMap + AlphaMode Transparency authored AHEAD of runtime (Rojo model files / Studio),
one per mesh texture, cloned onto the EditableMesh part at runtime. Open: whether vertex alpha is honoured together
with a ColorMap'd SurfaceAppearance (not measured yet); the cost of a SurfaceAppearance per layer.

## Cost (2026-10-16)

| what | measured | note |
|---|---|---|
| VfxMesh `wobble` deform (every vertex `SetPosition` each frame), flame = 41 x 17 = 697 vertices | 15 layers 3.7-4.0 ms, 30 layers 7.6-8.5 ms, 60 layers 14.2-17.0 ms of Luau per frame (two runs) | ~0.25 ms per flame layer, ~0.36 µs per vertex: 60 wobbling flames alone exceed a 60 fps frame (16.7 ms). Budget wobble to <= 10-15 layers, or fewer rings / segments |
| VfxMesh `cell()` (a flipbook cell = one UV rewrite, cards count 1) | 0.017 ms per call | free |
| Highlight on 2 parts | render CPU within noise | Studio unfocused (~20 fps, render CPU ~190 ms) — re-measure focused |

Studio unfocused throttles to ~20 fps and its `Stats.RenderCPUFrameTime` reads ~190 ms: render-CPU numbers from an
unfocused Studio are not the effect's cost. Luau time (`os.clock` around the work) is reliable either way.

## Shapes and drawing (2026-10-16)

| what | measured | verdict |
|---|---|---|
| a **Highlight** (outline, FillTransparency 1, AlwaysOnTop) on an EditableMesh MeshPart and on a Part | 0 green pixels off -> 1006 (mesh) / 1342 (part) on (facts_002/003) | **WORKS** on runtime meshes |
| VfxMesh **cards + cell()** (a mesh flipbook) | cell 0 vs cell 6 of a 4x4 sheet differ (mean 14.3, 18 % of the card's pixels) (facts_004/005) | **WORKS** — but on an opaque card (see TextureID alpha above) |
| an EditableMesh MeshPart's **pivot** | a tube built from y = 0 up sits with its FOOT at the part's position, not its centre | the part's CFrame is the mesh origin, not the bounding-box centre (VfxStage's `pivot = "base"` handles tube / cone / flame / ...) |

## Older measured facts (from the lessons)

Beam textures run the image's vertical axis along the beam; `Beam.FaceCamera = false` is a one-sided wall; a
ParticleEmitter with TimeScale 0 still emits (freeze = Enabled false); two ColorCorrections add; a 4x4 sheet on a
sprite without a flipbook draws 16 blobs; squash needs VelocityParallel. See [[vfx/index]] for the lesson notes.
