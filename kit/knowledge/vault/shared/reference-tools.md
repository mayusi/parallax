---
kind: reference
area: shared
date: 2026-10-16
source: VETLOG.md, kit/skills/parallax-3d Stage 1, kit lessons 3d (2026-10-06..08), ui (2026-10-11)
links: ["[[3d/index]]", "[[ui/index]]", "[[vfx/index]]", "[[world/index]]"]
---

# Reference tools and their licences (the input is the weak link; gather before any shape)

| Source / tool | Licence | Used for | Command |
|---|---|---|---|
| Openverse, Wikimedia Commons, The Met, Cleveland Museum APIs | per picture: CC0 / PD / CC BY / BY-SA only (NC, ND, unknown refused); creator + source recorded in refs/SOURCES.md | reference pictures | `kit refs find / expand` |
| USPTO design + utility patents | public domain (37 CFR 1.71(d) caveat) | cross-sections, exploded views, every internal part | `kit refs patent` |
| Sketchfab CC library, Smithsonian CC0 scans | per model | reference MODELS to measure and trace from (every side, every section a photo cannot give) | `kit library find / get / inspect` |
| A maker's 360° turntable | measure-only | a calibrated visual hull at the published length | `kit refs hull` |
| Wikidata / Wikipedia / the maker's spec page + owner's manual | A/B/C/D graded facts, quote-verified | sizes, variant tells, parts lists | `kit dossier`, `kit refs dims` |
| physicallybased.info (86 measured materials), ambientCG scans (CC0) | CC0 | real albedo / roughness / metalness; scanned surfaces | `kit materials` |
| Infinigen asset factories (BSD-3, numbers only) | BSD-3 | real-world size ranges per object kind | `kit/real_sizes.json` |
| Steam appdetails API, MediaWiki File URLs | measure-only stills | real game screens for UI identities (never a bot-check bypass) | `kit ui refs` |
| game-icons.net (CC BY, auto credit), Kenney (CC0) | per pack | icons, prompts | `kit ui icon find` |
| Creator Store (verified creators), DevForum uploads | per asset; VETLOG | native R6 animations (the quality bar; calibration data only) | store_pull route |
| yt-dlp (vetted 2026-10-15) | clips are private, measure-only | a scene's frames for a VFX breakdown (the owner's yes per source) | `kit vfx breakdown` |
| Freesound (CC0 filter, the owner's key), Kenney audio, Sonniss GDC, OpenAIR IRs, the Creator Store's licensed audio | per sound | real recordings | `kit sfx find / index` |
| USGS 3DEP (public domain), Copernicus GLO-30 (attribution), OpenTopography (key) | per dataset | real elevation for terrain | `kit world terrain --dem` (world mission) |

Rules: non-CC pictures of a real object are fine for a PRIVATE asset as measuring references (never shipped, never
committed; `refs/private/`); a NAME alone must still work (name-only research is strong); the owner's photos are
grade A when given; reject a bad reference model the moment it shows (mess, holes, scan noise, staging, a lying
label); a web search ranks content farms above the maker (`kit/knowledge/sources.json` blocks them); a number counts
only when a script finds it verbatim in the live source.
