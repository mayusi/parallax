<!-- reference for the parallax-ui route card; verbatim from the skill page (2026-10-16) -->

## Gates
Errors: unknown identity · hero/aaa without identity · contrast < 3 · text < 12 px · unknown type/font/colour/
style/slot/art/plate/ease · duplicate names · bad motion / insets / scale · **a hero screen's hero piece (`hero`, else
`focus`) as a TYPED font glyph** (letter it, render it, or make it a digit-set `number`; the one exception is the
identity's `"typed_hero_evidence": "<one of its references' image>: <what the still shows>"` — a realistic HUD's
typed readout, FieldHud) · a number node with no text, a character outside its `charset`, a `pitch` outside 0.5..1.2.
Warnings (the AI tells): the habit face (Gotham…) under an identity · an indigo / purple accent · one radius on
everything · a menu entering all at once · flat panel · no type hierarchy · centre blocked on a HUD · text over
the world without an outline · contrast < 4.5 · text < 14 px · touch target < 44 px · under the identity's
`minimums` (text / button / icon floors) · art not uploaded.
Typography + palette (v7.13): a hero screen warns sizes closer than 1.12x ("two levels that missed"); a counter rolling
in a proportional face warns (digits jitter: a digit set or a mono face); `palette_count` (more than 7 colours over 2%
of the painted area) and `palette_balance` (no colour over 40%: the 60-30-10 rule). Light direction across pieces is
NOT measured yet (it needs per-piece shading analysis).
Photosensitivity (v7.1): every reel counts its flashes (kit/ui/flash.py, WCAG 2.3.1): more than 3 a second over a
quarter of a 10-degree field FAILS the reel (red stricter); `Ui.setReduceFlashing(true)` stills split / flicker / ping.
Craft lints on the desktop frame (v7.2 / v7.3): `near_align` (edges or centres 1-3 px off a sibling's), `uneven_gap`
(3+ siblings 1-4 px off even spacing), `squint` (blur the frame: the spec's focus outside the top 3 regions warns).
Motion from footage (v7.6): `kit ui motion-ref <clip>` measures start / settle / ease / stagger of what moves.
Regression (v7.7): `kit ui diff` compares every screen with its GOLDEN (`kit ui diff <Screen> --approve` when the owner
rates it >= 7) and boxes what changed.
The owner's eye (v7.16): `kit ui ab <A> <B>` (two screens, or two PNGs + `--name <Screen>`) shows them BLIND as X / Y
in a random order on a local page; X / Y / = then a score records `kit verdict screen <winner> ... --vs <loser> --tag
ab`. `kit ui glance <Screen>` is the FIVE-SECOND TEST: `build/judge/ui/<Screen>/glance/` holds the frame at 640 px +
a brief for a fresh reviewer (look once, answer from memory: for / first / key / press) and the answer key (the focus,
its words, the squint rank — never shown to the reviewer); `kit ui glance <Screen> --check <answers.json>` fails when
what was seen first is not the focus. `kit ui saliency <Screen>` (V4 UI-X) MEASURES the first look: a blur+contrast
saliency map (luminance + colour-opponent centre-surround, an edge / text channel, a squint, UEyes' top-left location
prior), 24 simulated viewers each take their first look at its peak; under 85% on the focus (or within ~1 degree of
it) fails and names what took the eye (`build/judge/ui/<Screen>/saliency/map.png`). Its weights are UEyes-informed
defaults until `kit ui saliency calibrate --ueyes <folder>` fits them to UEyes' 1-second fixation maps (the dataset is
the owner's download, vetted first). `kit ui saliency gaze <Screen> --vlm | --points <json>` is the UIGaze protocol:
the local VLM's gaze points vs the map (CC / KLD) - VLMs match LATER, semantic looks, so it is never the gate.
The Combat Feedback Kit (V4 UI-X 13.6; rules in `src/kit/UiCombat.luau`): a `marker` whose `margin` is under its own
half-size (the pin hangs off the edge) or half a phone's height, and a `ladder` (hit / crit / kill streak banners:
`rungs`, `killWindow`, `hitWindow`, `hitStep`, `max` 1-6) the runtime cannot honour, fail the compile. `kit ui guide <identity>` writes the identity's STYLE GUIDE page
(`build/ui/guide/<identity>.html`: tokens with their contrast, the type roles in their real faces, shape / motion /
lettering / bans, the references, the drawn pieces, every screen wearing it) — hand it to whoever makes the next screen.
Languages (v6.13): `kit ui loc <Screen>` renders a pseudo-translation ("[Ŝĥöþ ····]": accented, 40% longer,
bracketed) on desktop + phone and lists what breaks, and lists every LETTERED word (a picture: Roblox's
AutoLocalize never translates it) — each needs a version per language or a typed fallback -> build/ui/loc/<Screen>.json.
Edge data (v6.12): `kit ui fuzz <Screen>` renders it with every word 60% longer and every number at 9,999,999 on
desktop + phone, and lists only what that BREAKS (overflow, squeeze, off screen, a digit-set number with too few
cells) -> build/ui/fuzz/<Screen>.json. Run it before calling a menu done.
Accessibility (v6.7): every screen is judged over its identity's GAME FRAME (`kit ui ground <identity> --world
<World>` -> assets/ui/grounds/, never uploaded; a hero screen warns `painted_ground` without one); text over a busy
ground is measured against the worst 10% of the ground right around its strokes (`busy_contrast`, XAG 102: 4.5:1,
3:1 for 24 px and up); `<Screen>.cvd.png` shows the frame to protanopia / deuteranopia / tritanopia players; a state
told by HUE alone warns (XAG 103).
Preview: text overflow, off screen, under the Roblox top bar, phone touch targets, an empty panel (a grounded
panel whose content covers under half of it — a judge's "dead space"; desktop view only), SQUEEZED pieces (two texts,
or a text and a small picture, overlapping on a device — only what shows counts).
The stage board (`kit ui plan`) locks the hero route: no ≥ 2 stills of the screen type at ≥ 1080p → every later stage
LOCKED (selftest fixture `kit/selftest/ui/refs_too_small`); no piece on a golden route → the pieces stage is open. `kit verify` fails if
`src/ui` drifts from the specs.
