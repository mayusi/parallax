<!-- reference for the parallax-ui route card; verbatim from the skill page (2026-10-16) -->

## The spec (full shape: top of `kit/lib/ui.luau`)
```json
{ "name": "RpgHud", "identity": "souls", "quality": "hero", "kind": "hud", "insets": "device",
  "scale": { "phone": 0.72, "tablet": 0.88 }, "root": { … } }
```
Node types: `panel label button image imagebutton scroll bar input canvas viewport` + identity nodes `plate`
(`"plate": "frame"`), `divider`, `texture` (`"texture": "grain", "strength": 0.1`), `counter` (`"value": 14352`,
rolls in game), `stat` (`label`, `value`, `delta`, `plate`, `valueWidth`) + components `crosshair hitmarker ring
scope keyhint ammo feed vignette` (an identity's own keycap / vignette / ring / glow replaces the kit's).
- Text: `"role": title|heading|body|hint|number` (+ the identity's own, e.g. `death`), `"tracking": 0.3` (letters
  set apart — YOU DIED — one auto-sized label per glyph), `textOutline`, `textGradient`, `rich`, `autosize`.
- Buttons / labels / stats / panels / imagebuttons: `"plate": "highlight"` puts the identity's piece behind the
  text (the selected row); a panel or an imagebutton with a plate IS that piece (a bubble button with an icon and
  a label inside — the simulator idiom). `"shadow": true | px` adds the dark offset copy under the plate (the
  sticker look). `"rarity": "epic"` = the `card_epic` plate + a `Kit_Rarity` attribute. A plate's colour is the
  contrast ground of the text on it (dark text on a cream pill passes; white on green needs `textOutline`).
- Counters: `"format": "short"` rolls 1.2K / 3.4M (simulators); `"full"` (default) 14,352.
- **States** (a pro screen designs every control's states, not just idle): `"states": {"hover": {...}, "pressed":
  {...}, "selected": {...}, "disabled": {...}, "locked": {...}, "new": {...}}`, each overriding `color textColor
  imageColor strokeColor` (theme names / #hex), `transparency textAlpha imageAlpha` (0..1), `image` (`art:` swap),
  `text`. A plate button's picture overrides reach its Plate and its words its Label. `kit ui` draws
  `build/ui/<Screen>.states.png` (every control, idle beside each state); a hero screen WARNS while a button has no
  states. In game: `Ui.setState(node, "disabled")` (nil = idle; selected / disabled / locked / new are sticky, hover
  and pressed are wired by Ui.bind and wait under them; disabled / locked stop the button).
- **Live 3D showcase**: a `viewport` node (`"model": "<KitModels name>"`, `"spin": 0.4` rad/s, `"lightColor"`,
  `"ambient"`) also takes `"lightDirection": [-1, -1, -0.5]` (the key light) and `"drag": true` — the player turns
  the model with a UIDragDetector, its spin pausing while held (the AAA character / item inspect; a pre-rendered spin
  flipbook stays the route for a piece that must look identical everywhere).
- **Flows** (design the way between screens, not single screens): `assets/ui/flows/<Flow>.json` — `start` + `steps`
  of `{"from", "to", "on": "<button path>", "transition": "fade" | "push" | "shared", "shared": {"from": "<piece>",
  "to": "<piece>"}}`; `kit ui flow <Flow>` checks it (real screens, a button to press, shared pieces that exist, a
  way back to the start) and films it (build/ui/flows/<Flow>.gif, saved in library/ui/flows/). In game
  `Ui.go(from, to, {transition = "shared", shared = {a, b}})` throws piece a on an arc into piece b's place.
- **StyleSheets** (a game's OWN hand-made screens wearing an identity): `kit ui style <identity>` ->
  `src/ui/styles/<identity>.model.json` (tokens as `$Token` attributes, 8 rules, the hover timing as a styling
  transition); in game `Ui.link(myScreenGui, "<identity>")`; tag pieces KitTitle / KitPanel / KitPrimary / KitMuted.
  Re-run it after changing the identity. NATIVE.md has the evaluation.
- **Sound** (the SFX lane makes the sounds; a screen names them): `"sounds": {"hover": "UiHover", "press":
  "UiClick", "enter": "MenuOpen", "show": "Pop", "selected": "UiConfirm", "disabled": "UiError", ...}` — Sfx events
  checked against assets/sounds/_events.json; Ui fires each on the frame its moment LANDS (an enter at its delay + 80%
  of its motion, a state when Ui.setState sets it). Grammar: confirm rises, cancel falls, hover near silent, the big
  moment richer; one source palette per identity (`kit sfx set`).
- **Atlases** (automatic): the plates step packs every identity's small pieces (<= 256 px, not 9-sliced) into
  1024 sheets (`atlas_<n>`, uploaded like any art); a compiled picture whose piece is in an uploaded sheet shows the
  sheet through ImageRectOffset / ImageRectSize — fewer textures to stream (`Kit_Atlased` on the screen counts them).
  Flipbooks, digit cells and state picture swaps keep their own uploads; the preview draws the piece itself.
  **Held art** (`assets/ui/upload.hold.json`: pieces derived from a real character's pictures) is never uploaded by
  `kit upload` and never packed into a sheet.
- **World-space UI** (nameplates, damage numbers, markers, screens ON parts): `"space": "world", "world": {"kind":
  "billboard", "offset": [0, 3, 0], "maxDistance": 140, "onTop": false, "distance": {"near": 18, "far": 110, "min":
  0.55}}` or `{"kind": "surface", "face": "Front", "light": 1}`; the root's pixel size is the canvas. It compiles to a
  BillboardGui / SurfaceGui TEMPLATE: in game `Ui.attach(template, part)` mounts a copy (a billboard with "distance"
  shrinks between near and far), `Ui.floater(template, position, "128")` flies a damage number up and clears it (its
  "Value" label gets the text). The preview draws it at near / mid / far over the world (examples: RiffNameplate,
  RiffDamage).
- **UI particles** (Roblox has none in 2D: pooled sprites): presets on the identity (or the screen) `"bursts":
  {"smash": {"sprite": "art:spark", "count": 22, "life": 0.5, "speed": [950, 1900], "spread": 360, "angle": -90,
  "gravity": 2200, "size": [36, 78], "spin": 360, "colors": ["accent", "#ffffff"], "fade": true, "shrink": true}}`;
  a node's `"burst": "smash"` (or `{"preset", "on": "show" | "manual", "delay"}`) fires it when the node shows; the
  reel draws the same seeded flight (a `{"macro": "burst", "node", "at", "preset"}` fires one at a time). Kit
  sprites: `spark` (four-point star), `shard` (a sliver), `disc`, `glow`; or an identity piece. Save them for the
  BIG moment (a hit, a level-up, a win) — never on idle screens.
- **Vector lines** (`"type": "path"`, Roblox Path2D — crisp at any size, NO upload, no moderation wait): `"points":
  [[x, y], ...]` (px in the node's box) or `"arc": {"from": 200, "to": 340, "r": 0.46}`, `"color"` (the stroke),
  `"thickness"`, `"smooth"` (default true), `"closed"`, `"outline": {"color": "shadow", "px": 1}` (a darker stroke
  under it, for lines over the world), `"draw": {"dur": 0.6, "delay": 0}` (it strokes itself on when shown). A
  Path2D has no transparency: dim a line with a darker colour. Use it for rules, arcs, outlines, speed lines —
  anything a baked PNG line would be (FieldHud's magazines are paths).
- **Gamepad / console**: the screen's `"firstFocus": "<path>"` is where the pad lands when it opens (a hero screen
  with 2+ buttons warns without one); `"nav": {"up": "<path>", "down", "left", "right"}` on a button overrides the
  engine's d-pad neighbour (wrap a tab row: the last tab's right is the first); a keyhint's `"glyph": {"pad":
  "ButtonX", "touch": "hide"}` shows the pad button's picture while a pad is in use and hides on phones. The
  selection wears the identity's drawn outline (`"focusPiece"` on the screen or identity, else its `frame_line`)
  instead of the engine's blue box. `kit ui` draws `<Screen>.focus.png` (where the pad lands + every nav link);
  in game `Ui.gamepad(screen)` (UiMotion calls it) wires it all.
- **Bitmap-font text (v7.5)**: `python kit/ui/font.py <identity>/<set> --font <face> [letter style flags]` letters
  the whole printable alphabet (case-safe file names), measures each glyph's ink and reads the face's own kerning;
  a label with `"glyphs": "<identity>/<set>"` is then set in it — any text, proportional, kerned, wrapped, aligned;
  `Ui.write(node, "any words")` in game; `"glyphFx": {"kind": "wave" | "shake" | "pop", "amp", "speed"}`.
- **Menu backdrop (v7.4)**: `"backdrop": {"blur": 18, "darken": 0.35, "saturation": -0.4}` on a menu screen — the world
  blurs, darkens and greys while it is open (Ui.backdrop; the preview draws it over the ground).
- **HUD systems (v7.8)**: `marker` (Ui.track(node, part): over the target, pinned to the edge with an arrow when not,
  behind-camera safe, stacked), `compass` (`"degrees": 180`, follows the camera), `damage` (Ui.hurt(node, from)),
  Ui.fly(from, counter, {count, preset}) for coins into a counter.
- **Menu systems (v7.9)**: `toasts` (Ui.toast queue), `tooltip` + any node's `"tip": {"title", "lines": ["+12 ATK"]}`
  (green / red by sign), Ui.modal / Ui.back (Escape / gamepad B closes the top), Ui.loading(screen, assets, tips),
  Ui.coach({{target, text}, ...}) for a first-time spotlight tutorial.
- **Roblox's own UI (v7.10)**: `Ui.chat(screen)` dresses TextChatService's window, input bar and bubbles in a kit
  screen's tokens + font; `Ui.core({health = false, backpack = false, playerList = false})` hides what the game replaces.
- **Console / phone (v7.11)**: `"console": true` on a screen = the TV checks (title-safe 90%, text >= 24 px); every
  phone sheet warns a control centred in the top middle (the hardest thumb reach).
- **Haptics + funnels (v7.12)**: `"haptic": {"press": "light" | "heavy", "selected": ...}` pulses with the sound
  moments (Ui.haptic); the server declares flows with `kit.UiAnalytics.start({Shop = {"open", "tab", "buy"}})` and the
  client reports a step with `Ui.funnel("Shop", 2)` (one validated, rate-limited remote; AnalyticsService funnels).
- **Wipes + settings (v7.14)**: `Ui.wipe("shutter" | "slash" | "blinds", {onCovered = swap})` covers the screen in the
  identity's accent while you swap screens / teleport; `Ui.setTextScale(1.25)`, `Ui.setHighContrast(true)` and
  `Ui.setReduceFlashing(true)` are the player settings. `kit ui loc --export build/ui/loc/LocalizationTable.csv`
  writes every text (and every lettered picture to re-letter) as a Roblox LocalizationTable.
- **Data + lists + budgets (v7.15)**: `"bind": "player.coins"` on a label / counter / bar / number / glyph text follows
  `Ui.set("player.coins", 1250)`; `Ui.list(scroll, items, render, rowHeight)` keeps only the rows in view (a pool
  recycled as it scrolls); every screen carries `Kit_Budget` (instances, distinct pictures) and a hero screen warns
  past 1500 / 80.
- **Runtime fx** (UI "materials" — Roblox has no UI shaders, so each is built from engine pieces): `"fx": [{"kind":
  "shimmer"}, ...]` on a picture, a text or a panel. `shimmer` (a light band sweeps it: `period width alpha angle
  color delay`), `ping` (an echo grows and fades — a beat, a "ready": `period scale alpha color`), `burn_in` (a lit
  wipe reveals it once when shown: `dur soft angle edge`; not on a node with its own gradient), `split` (a chromatic
  glitch: `px every dur alpha colors`), `flicker` (hologram dips: `every dur depth`). A picture's fx draws from its
  GLINT (`<piece>__glint`, the white silhouette the plates step makes; upload with `kit upload --only __glint`). The
  reel plays them as Ui.fx does; reduced motion keeps them still. Pick by the SOURCE: chrome gets a shimmer, a
  rhythm game's rank pings on the beat, a glitchy title splits — never sprinkle all five.
- Bars: `fill`, `fillGradient`, `"ghost": true` (the pale damage trail that drains late), `"caps": true`
  (ornamental end pieces, `capSize`), `stroke`; every fill carries a lit core hairline (`"core": false` to drop it);
  `"track": true` makes the identity's chunky track the bar's ground and `"fillGloss": true` lights the top half
  of the fill (the candy bar); a `plate` child at `pos: ["70%", "50%"]` is a slider knob.
- **Phone reflow:** `"at": {"phone": {"size": [...], "pos": [...], "anchor": "center", "textSize": 18, "visible": false},
  "tablet": {...}}` on any node — the preview's phone/tablet sheets and the runtime (`Ui.scale`) apply it; in Studio
  set `Ui.forceViewport = "phone"` then `Ui.scale(screen)` to see it at any window size. Hide a second column, widen
  the first, lift a toast. `"scale": {"phone": 0.72}` on the screen shrinks everything; `at` moves things.
- The selected row idiom: `"plate": "highlight"` on the row + a child `{"type": "plate", "plate": "arrow",
  "rotation": 90, "pos": [-22, "50%"], "anchor": "right", "motion": {"loop": "breathe"}}` as its gold marker.
- Layout: `{"dir", "gap", "align", "justify": start|center|end, "wrap"}` or `{"grid": [w, h]}`; slots for HUD
  conventions; `"100%-24"` edge positions; `aspect`; `clip`; `z`.
- Images: `"image": "art:<name>"` (kit) / `"art:<identity>/<name>"` (plates, your icons) / `rbxassetid://…`,
  `"fit": fit|crop|stretch|tile` (+ `tile` px), `imageColor`, `imageAlpha`, `slice`.
- `viewport`: `"model": "<ReplicatedStorage.KitModels name>", "spin": 0.4` — a kit 3D model inside the screen.
- `number` (a DIGIT SET, drawn not typed): `{"type": "number", "digits": "<identity>/<set>", "aspect": <the set's>,
  "text": "888" (its WIDEST text: the cells are laid for it), "size": [w, h], "align": center|left|right,
  "charset": "0123456789+x" (default the ten digits), "pitch": 0.78 (the advance as a share of a cell, 0.5..1.2: a
  chunky set with an outline reads spaced at 1)}` — a frame of image cells; it keeps `motion`, `rotation`, `at`; it
  can be the focus; in game `Ui.number(node, "182")`; in a reel a `text` track swaps its cells.
- `"lettering": true | {...}` on a label / button: the text becomes lettered art (the identity's `"lettering"` block
  as defaults: `style`, `font`, `weight`, `fill`, `ink`, `outline`, `shadow`, `lean`, `track`, `inline`, `glow`...; colour
  names resolve through the tokens); the node's own textSize / role / textColor / textOutline / tracking go away.
- `"ground": "<token or #hex>"` on a panel with no fill: the colour of the ART under its text, so contrast is
  measured against the picture, not the screen.
- `"hero": "<Root>.<Node>"` names the hero piece when the focus is not it (the composition gates and the typed-glyph
  error read it).
