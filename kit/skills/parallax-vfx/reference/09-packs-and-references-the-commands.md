<!-- reference for the parallax-vfx route card; verbatim from the skill page (2026-10-16) -->

## Packs and references — the commands
- `kit vfx import <dir> --prefix kn --pack "Kenney Particle Pack 1.1 (CC0)" [--alpha glow|coverage] [--color gray]
  [--cell 512]`: every PNG under the directory becomes an `import` spec (existing specs kept); then `kit vfx`.
  Imported so far: Kenney Particle Pack (80, kn_*), Kenney Smoke Particles (77, ks_*), Unity Labs HDR sequences
  (ul_explosion_light, ul_explosion, ul_wispy_smoke, ul_cloud). Every pack: a VETLOG.md row first (licence quote,
  hash, what was inspected). `build/textures/_library.md` lists textures by pack.
- `kit vfx refs <preset> <url|file|dir>... [--frames 6]`: stills into `assets/effects/refs/<preset>/` (git-ignored):
  images copied, GIF / WebP / video turned into spread frames + the brightest one, sources logged in SOURCES.md.
  Wikis refuse plain clients: the tool sends a browser user agent. The viewer's refs panel and `kit vfx judge` use
  that folder.
- **TEXT FIRST — what the attack IS (owner 2026-10-14: "vision alone isnt working out u need both vision and detailed
  text")**: `kit vfx refs lore <set> <wiki:Page | URL>... [--search "<words>" --wiki <fandom>] [--pages 6] [--about
  "<words>"]` digs the article text (MediaWiki API: the technique's page, the character's, the EPISODE pages where the
  scene is described; any https page's visible text), keeps wiki TABLES as sentences (the variant tables hold the visual
  facts: "In Bankai, the Getsuga Tenshō is black, can have its path controlled, and possesses explosively augmented power
  and speed"), skips trivia/other-media, and on off-topic pages keeps only sentences naming the subject. Facts tagged
  colour/shape/scale/power/motion/sound/variant -> `refs_measured/<set>.lore.json`; full text -> `refs/<set>/LORE.md`.
  `kit vfx refs brief <set>` joins them with the measured palette/shape -> `refs_measured/<set>.brief.md`: READ it, and
  build every fact (scale, speed, what it does to the world, how the variant differs) — cite them in the generator's
  docstring (example: `getsuga_bankai_v3.py`). `refs measure` warns while a set has no lore, and `kit vfx refs norms
  <effect>` rule 5 FAILS unless the generator quotes >= 3 of the set's lore facts (examples: `spirit_bomb_v3.py`,
  `kamehameha_v4.py`). Video-game skill-list lines are scored out of the brief; a proven mechanic (a tube stack) is
  reused and changed where the text says (2x the user), not reinvented.
- **The details decide quality (owner 2026-10-15)**: look at every ELEMENT close up, alone. Air / energy / fire is
  never a solid surface: every big mesh gets a detail texture (wind_streaks / wind_streaks_v for gusts, ki_wisp_streaks,
  ki_cells ...), soft edges (fadeIn / fadeOut / fadeSides) and an erode dissolve; rings that ride a flow are feathered
  mesh discs facing it; streak sprites come from a small volume at varied speeds, thin. `refs norms` rule 6 fails bare
  solid meshes. Example: rasengan.py's blow-out (gust shells + swirl + rings).
- **The outline as numbers (`kit vfx refs silhouette <set> --effect <name> [--times a,b]`)**: aspect, taper, flame
  tips on the top edge, notch depth, fill — measured on the uncut reference stills and on our render, with what to change
  in the mesh shapes. UNTRUSTED under 8 uncut stills (wiki stills are mostly close-ups) and when the subject shares the
  effect's colour (golden hair in a golden aura): read it, never apply it blindly.
- **Impact frames are for MASSIVE hits only** (owner 2026-10-14: "not everything has to have impact frames unless ur
  gonna make it really massive"). A slash release, a charge, an aura: no impact frame — a 2-frame tint/contrast flash at
  most. `beats.py` defaults to `--frame none`. One per effect, on the landing of a world-shaking attack (Black Flash, a
  Bankai Getsuga's explosion).
- **The reference loop (2026-10-14 — use it for every effect from a real source; never show the owner an uncompared
  render)**: `kit vfx refs wiki <set> <wiki:Page>...` (every image on whole MediaWiki pages via the wiki's API, e.g.
  `dragonball:Kamehameha`; a page with 0 images = a wrong title: the tool prints the wiki's real ones; image hosts
  allow-listed) -> `kit vfx refs rank <set>` (stills scored by effect-colour coverage, hue band found by itself; LOOK
  at the numbered sheet `build/vfx/refs/<set>_rank.png` and pick the frames that show the effect) -> `kit vfx refs
  measure <set> --pick 1,4,9,...` (luminance bands: share + colour, saturation -> `assets/effects/refs_measured/<set>.json`,
  committed) -> build to those numbers -> record -> `kit vfx refs compare <set> --effect <name>` (0-100 colour match +
  render-beside-refs sheet). Measured colours are what the frame SHOWS: additive Neon layers stack and wash out, so
  feed them pre-saturated (x1.6 yellows .. x2.4 reds/oranges) and keep whichever version compare scores higher.
  compare judges COLOUR only: shape and timing are still read off the sheet. Proven: Saiyan forms (Kaio-ken 55 -> 80.8,
  Blue Kaio-ken 88.7), Kamehameha 64.6 -> 86.8 (517 frames).
- **Flipbooks on meshes**: a mesh layer takes `"flipbook": {"layout": "4x4", "fps": 16, "mode": "Loop|OneShot"}` (its
  UVs step from cell to cell: VfxMesh `cell()`), and the `cards` shape (`params.count` crossed vertical planes through
  the axis) gives a drawn flipbook depth. `python kit/vfx/meshify.py <preset> [--as <new>]` turns every one-particle,
  camera-facing, emissive flipbook card of a preset into such mesh cards (the original is never touched; output
  `<preset>_meshaura`). The owner's favourite look is this HYBRID: meshes for volume + the hand-drawn flipbook for the
  anime silhouette (saiyan_ssj_3d); an all-mesh rebuild without the drawings was rejected.
- Effect generators (the Python that writes a preset) live in `assets/effects/generators/` beside their presets —
  never in `_scratch/` (git-ignored).
- **No-hands loop (2026-10-14)**: `python kit/vfx/autorec.py <effect>... [--views hero,cine,player] [--compare <set>
  --times 2.6,3.6]` records with a HEADLESS local Edge/Chrome (same score as a hand-driven recording; it tree-kills its
  browser — orphaned headless Edges once starved the GPU). `python kit/vfx/fit.py <effect> <set> [--times ...]` grades
  every colour (saturation x gain), records + scores each grade, keeps the best as `<effect>_fit` (UI Sign 82 -> 86.9,
  Mastered UI 58 -> 83.2, Spirit Bomb 73.5 -> 87.1). A SHORT effect needs `--times` (moments it is on screen).
- **Timing rules (research: Riot style guide, realtimevfx critiques, 80.lv)**: `kit vfx refs timing <effect>` reads the
  recording's luminance curve: an anticipation DIP right before the climax (a 0.05-0.12 s screen darkening), a SNAPPY
  climax (attack <= 0.25 s: the release lands in 1-3 frames), a SHORT dissipation (<= 40 %), climax contrast. Fix what
  it flags (Kamehameha v1 2/4 -> v2 4/4).
- **Stylized mesh motion**: mesh layers take `"step": 12` (the clock held on drawings: on twos, the anime cadence) and
  `"erode": [start, end, soft]` (a per-vertex noise dissolve instead of a fade — coarse on big triangles: no per-pixel
  shaders in Roblox; dense meshes or a baked eroding flipbook for crisp holes). `python kit/vfx/animepass.py <preset>`
  applies both to every mesh layer (new preset `<preset>_anime`).
- **Shapes added for references**: `corona` (sharp blades out of a sphere: energy balls, starbursts), `arc` with
  `vertical: 1` (a standing crescent flying +X: slash waves), `cards`, `spikes`, `bolt`; textures `ki_cells` (worley
  skin), `ki_rays` (streaks on a light floor). Black on additive layers: a toon SmoothPlastic mesh, OPAQUE, with no
  glow over it (bloom smears bright rims across it — the Bankai Getsuga still reads dark-pink: open).
