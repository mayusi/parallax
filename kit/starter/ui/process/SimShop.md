# SimShop — the process (an exemplar: copy HOW it was made, never the look)

Identity `sim`, kind `menu`, quality `hero`, focus `Shop.Window.Title.Txt`. Written by `kit/ui/exemplar.py` from the screen's files.

## 5 The verdicts (first: the owner's eye is the bar)

- the owner has not rated this screen
- fresh judges: 2 — median 65.0 (judges underrate the owner by 30-45 points: read them for BUGS)

## 1 The stills (the source is the ceiling)

- none recorded: `kit ui refs <id> "<game>" "<screen words>" --rank ...` then `--index` / `--tag`

## 2 The identity

- tokens: bg #0f1b36, panel #fff8ea, panel2 #eadfca, line #1b2a4a, accent #ffc93c, accent2 #ff9f1c, text #ffffff, textDark #1b2a4a, muted #7f8caa, danger #ff4d4d
- fonts: {"font": "FredokaOne", "titleFont": "LuckiestGuy", "monoFont": "FredokaOne"}
- lettering defaults: {"style": "flat", "font": "luckiestguy", "fill": "text", "ink": "line", "outline": 0.09, "shadow": 0.07, "shadow_color": "shadow", "lean": -2, "track": 0.03}
  - evidence: the sim identity's own rules (bans: 'white text without an outline over the world', outline weights 5 at 48 px = 0.1 em, chunky drop shadow 6): the typed Luckiest Guy titles became lettered art (hero_

## 3 The pieces, by route (the medium is the lever)

| node | piece | route | standing | remake it with |
| --- | --- | --- | --- | --- |
| `Shop.Window.Title.Icon` | `sim/icon_cart` | concept | caution | green shopping cart (PROVENANCE.md: a generator) |
| `Shop.Window.Title.Txt` | `sim/w_shop` | letter | golden | text SHOP; font luckiestguy; size 57; fill #ffffff; ink #1b2a4a; outline 0.09; shadow 0.07; lean -2.0; shear 0.0; track 0.03; arc 0.0 |
| `Shop.Window.Featured.Icon` | `sim/icon_chest` | concept | caution | treasure chest (PROVENANCE.md: a generator) |
| `Shop.Window.Grid.Pack1.Icon` | `sim/icon_coin` | concept | caution | gold coin with a star (PROVENANCE.md: a generator) |
| `Shop.Window.Grid.Gem1.Icon` | `sim/icon_gem` | concept | caution | blue diamond (PROVENANCE.md: a generator) |
| `Shop.Window.Grid.Boost1.Icon` | `sim/icon_potion` | concept | caution | pink potion (PROVENANCE.md: a generator) |

(29 small typed text(s) — the numbers that change, hints; never the hero)

## 4 The rounds

- 2026-10-16 feat(kit ui): THE HERO ROUTE LOCKED (mission 03 phase 1) - kit ui plan is seven locked stages (refs -> identity -> pieces -> assemble -> look -> judge -> promote; a stage after the first un
- 2026-10-10 feat(kit ui): the look record, focus, phone truth, the world backdrop, refs in the packet, kit ui plan
- 2026-10-10 feat(kit): weapon movesets — kit/anim/strike.py builds R6 clips from technique keys (grip + blade direction, torso, feet with steps, weight, look; both hands solved onto the hilt, pelvis on

Last look (mayusi): desktop: SHOP lettered in the green banner; tabs, starter pack and coin/gem cards unchanged

## 6 Redo it for a NEW game (the route, never this look)

1. refs: `lune run kit ui refs <id> "<game>" "<this screen type>" --rank "<what it shows>"` → `--keep` → `--index` / `--tag <file>=menu`; `kit ui read <still>` + `kit ui measure <still>` → REFS.md
2. identity: `lune run kit ui identity_from <id>` → merge into `assets/ui/identities/<id>.json` (tokens sampled, minimums, lettering defaults from `kit ui read type`)
3. pieces: the routes above, in the NEW game's own language — letter first
4. assemble: `lune run kit ui <New> --motion`; scale from the measured boxes (never a judge's word)
5. look: `lune run kit ui look <New> "<what you saw>"`
6. judge: `lune run kit ui verify <New> --pairs` → `kit ui verify <New>` → a FRESH model → `--record`; show the owner every round
7. promote: only on the owner's verdict (`kit verdict screen <New> <0-10> "<words>"`)
