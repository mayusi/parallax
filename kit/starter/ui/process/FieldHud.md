# FieldHud — the process (an exemplar: copy HOW it was made, never the look)

Identity `field`, kind `hud`, quality `hero`, focus `Hud.Ammo.Check`. Written by `kit/ui/exemplar.py` from the screen's files.

## 5 The verdicts (first: the owner's eye is the bar)

- **The owner: 80/100 — "OK great (owner, 2026-10-12, on v2 after calling v1 AI slop)"**
- fresh judges: 2 — median 61.0 (judges underrate the owner by 30-45 points: read them for BUGS)

## 1 The stills (the source is the ceiling)

- `assets/ui/refs/field/field_steam_03.jpg` — 1920x1080, world (>= 1080p)
- `assets/ui/refs/field/field_steam_07.jpg` — 1920x1080, world (>= 1080p)
- `assets/ui/refs/field/field_wiki_11.jpg` — 1920x1080, hud (>= 1080p)
- `assets/ui/refs/field/field_wiki_12.jpg` — 853x456, hud (UNDER 1080p: measure-only, never trace from it)
- `assets/ui/refs/field/field_wiki_17.jpg` — 1024x512, hud (UNDER 1080p: measure-only, never trace from it)

## 2 The identity

- tokens: bg #000000, panel #0b0e0f, panel2 #161b1d, line #000000, line2 #3c4446, accent #e0a63a, accent2 #f2d49a, text #eef0ec, muted #aab0ab, danger #d9483b
- fonts: {"font": "RobotoCondensed", "titleFont": "Oswald", "monoFont": "RobotoMono"}
- typed_hero_evidence: assets/ui/refs/field/field_wiki_11.jpg: the real HUD sets its hero readout (the magazine count) in plain tall condensed numerals with no lettering or effect - a realistic HUD's medium IS the typed rea

## 3 The pieces, by route (the medium is the lever)

| node | piece | route | standing | remake it with |
| --- | --- | --- | --- | --- |
| `Hud.Compass.Window.Strip` | `field/compass_strip` | drawn | caution | drawn by script: _scratch/ui_field/make_field_art.py (an original town, a 360-de |
| `Hud.Ammo.Mags.Current.Level.Fill` | `field/mag_fill` | drawn | caution | drawn by script: _scratch/ui_field/make_field_art.py `magazine()` — a curved rif |
| `Hud.Ammo.Mags.Current.Outline` | `field/mag_outline` | drawn | caution | drawn by script: _scratch/ui_field/make_field_art.py `magazine()` — a curved rif |
| `Hud.Ammo.Gear.Frag` | `field/icon_frag` | ink | golden | from build/vision/field_frag.png; mode icon |
| `Hud.Ammo.Gear.Flash` | `field/icon_flash` | ink | golden | from build/vision/field_flash.png; mode icon |
| `Hud.Mate0.Chev` | `field/chevron_down` | drawn | caution | drawn by script: _scratch/ui_field/make_field_art.py `chevron()` — a teammate ma |

(13 small typed text(s) — the numbers that change, hints; never the hero)

## 4 The rounds

- 2026-10-14 fix(kit ui): every SQUEEZE the new preview check found in older screens, phone/tablet only (desktop unchanged) — StriveDuel/Combo: the clock and the hit counter move clear of the health bla
- 2026-10-12 ui(FieldHud v2): realistic means reporting only what the player cannot feel (owner: v1 "looks like AI slop") — no minimap, crosshair, health number, round count or boxes; magazines drawn as
- 2026-10-12 ui(FieldHud): no game footage behind the HUD — the Insurgency backdrop removed (owner), the preview shows the HUD on the kit's neutral world; corner shade pools fainter
- 2026-10-12 feat(kit ui): FieldHud, a realistic tactical-shooter HUD from scratch by the hero route (refs from three shooters + the CoD wiki measured at 1:1, the field identity, a sunlit HUD-less backd

Last look (mayusi): desktop: unchanged by this round (only the identity's typed_hero_evidence: the magazine count stays a typed readout like the CoD still); compass, ammo block and hit text read thin over the dark preview world

## 6 Redo it for a NEW game (the route, never this look)

1. refs: `lune run kit ui refs <id> "<game>" "<this screen type>" --rank "<what it shows>"` → `--keep` → `--index` / `--tag <file>=hud`; `kit ui read <still>` + `kit ui measure <still>` → REFS.md
2. identity: `lune run kit ui identity_from <id>` → merge into `assets/ui/identities/<id>.json` (tokens sampled, minimums, lettering defaults from `kit ui read type`)
3. pieces: the routes above, in the NEW game's own language — ink first
4. assemble: `lune run kit ui <New> --motion`; scale from the measured boxes (never a judge's word)
5. look: `lune run kit ui look <New> "<what you saw>"`
6. judge: `lune run kit ui verify <New> --pairs` → `kit ui verify <New>` → a FRESH model → `--record`; show the owner every round
7. promote: only on the owner's verdict (`kit verdict screen <New> <0-10> "<words>"`)
