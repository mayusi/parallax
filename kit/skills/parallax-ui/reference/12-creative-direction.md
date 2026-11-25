# 12 — Creative direction (v8, 2026-10-24)

The owner: the craft "is not lacking anymore"; what fails is the DIRECTION when the ask is original — "take my bullshit
prompting and turn it into something out of this world". A director decides WHAT the screen is before anyone builds it.
`kit ui direct` (kit/ui/direct.py) is the discipline and the memory around that decision; the ideas are yours.

## The loop
```
lune run kit ui direct learn                                   the taste profile -> kit/knowledge/vault/ui/director.md
lune run kit ui direct new <name> --ask "<the owner's words, VERBATIM>" [--game G] [--screens hud,menu:shop]
lune run kit ui direct check <name>                            a design, not a wish
lune run kit ui direct board <name>                            sketch frames + build/ui/directions/<game>/<name>/board.html
lune run kit ui direct pick <name> <key> "<their words>" --by owner [--identity <id>]   ONLY with the owner's pick
lune run kit ui direct status <name> | --identity <path>
```
Then the hero route as always, from stage 1: the picked direction's `sources` become real stills (`kit ui refs`),
measured, and only then the identity's tokens are set from them (the draft's tokens are the direction's palette, marked
TO MEASURE).

## 1. Read the ask (never take a word literally)
The owner's words are loaded; `kit/ui/direct_lexicon.json` holds what each one PROVED to mean, with the verdict behind
it: "realistic" = absence (FieldHud v1 1/10 → v2 8/10); "like <game>" = its real screens measured; "Persona" = the
lettering; "cooler" = motion and a move from the source; "AAA / not AI slop" = change the medium; "original" = an
object of this world with its own verb, never a genre swap. `new` finds them in the ask; `check` fails until the brief
says how THIS piece reads each one. Add a lexicon entry only from the owner's own words + a verdict.

A mood word the vault has never read ("magical", "vibes", "cozy", "cinematic"...) is not skipped: `new` adds it as
`mood:<word>` and `check` fails until the brief says what it means HERE ("magical = the world responding to you, never
sparkle particles on panels"); the owner's verdict on the result is what teaches the lexicon.

Then the reading: the player's FANTASY, who the player is, and the MOMENT they look (a mid-fight glance is not a calm
menu). Write your assumptions down so the owner can correct them in one line.

## 2. Branch: 3-5 territories, not 3 colourways
Each direction is a metaphor: **the HUD IS <an object of this world>**. `new` lists the world's objects from its
blueprint (video wall, street lamp, car...) and its pitch. Pro UI is one of them: the health bar IS a guitar neck
(riff), the gauge IS a gunsmith's steel plate (the Umbra gauge, 8.5). A wish-word is never a direction: sleek,
modern, clean, futuristic, epic, premium, cool → `check` fails the big idea that leans on one.

The directions must DIVERGE on the four axes — `space` (screen / diegetic / hybrid), `volume` (quiet / loud),
`material` (paper, ink, metal, light, signage, pixels...), `voice` (world / character / observer / enemy / system):
every pair differs on at least two; their palettes sit apart (CIE Lab ≥ 18); their display faces differ (a warning).
At least one source per direction comes from OUTSIDE games (signage, broadcast, print, ritual, architecture, film):
that is where the unexpected comes from.

**Break the habit first** (`kit ui direct spark <name> [--n 12] [--seed N]`, kit/ui/direct_spark.py): forced
connections — an object of THIS world × a medium from outside games (a railway board, an ECG monitor, a tide table, a
hanafuda card... media already used by the brief or by an existing identity are left out) × a verb × a voice × a
constraint ("only two colours", "the UI damages when you do") × an inversion ("what if your health were visible to
everyone but you?"). Most sparks are wrong; read them all, keep the one nobody would reach by thinking straight, and
note it on the direction (`"spark"`). SampleCity's E, Skyline Pulse (the skyline as your ECG), came from one.

**Never print the source's names**: when the ask is "like <a source>", `context.source_names` lists what it OWNS
(characters, techniques, coined words) and `check` fails any frame or big idea that shows one. The first blind critique
called JJK's own 黒閃 / 無量空処 on the frames "the serial numbers left on" — take the grammar, name the moment ourselves.

**The swap test** (a branding check, in `check`): a direction whose idea's nouns belong to ANOTHER of the owner's games
as much as to its own is flagged — it is not "only here" (`swappable`: each game's blueprint things + pitch).

## 3. Each direction carries
a verb (how it MOVES: written, cut, flipped, breathing), ONE signature moment beat by beat (≥ 3 timed beats: the reel is
the pitch, not the still), `only_here` (why no other game could have it), a type voice from the Roblox catalogue, a
palette with its reason, the Roblox technique per element, the screens it becomes, sources to gather, a risk, and what
it is NOT (the lazy version). `check` also refuses a palette whose ground AND accent sit on an existing identity — a
re-skin (it caught the Veil direction sitting on `strive`; the fix was the truth: that direction is PAPER-dominant).

## 4. Show, then the owner picks
`board` draws each direction as a SKETCH frame on the game's own world shot (`frame.elements`: rect, bar, ring
(with `ry` for one lying on the ground), ellipse, text / vtext (vertical Japanese), stamp, dots (LED / halftone), scan,
line, glow, figure (a fighter's silhouette for a diegetic idea)) — labelled a test frame, never the art — plus the HTML
board with the palette, the type in its real faces, a plate in its shape language, the beats and the sources.
Recommend one; never record a pick the owner did not make (`pick` without `--by owner` is a proposal).

**The moment in motion** (`kit ui direct reel <name> [<key>...]`, kit/ui/direct_reel.py): "cooler" = motion, so the
pitch is the signature moment PLAYING. Time the frame's elements against the beats — `"t": [t0, t1]`, `"in"` /
`"out"` (alpha, dx, dy, scale; ease out / in / back / snap / linear), `"wipe"` (a reveal along x or y from start / end /
centre: a band closing like a door), `"pulse"` — and give `frame.reel` its duration and whole-frame beats (`invert`,
`white`, `black`, `shake`, `tint`, `desat`). It renders `<key>.reel.gif` + `<key>.strip.jpg` (six frames at the beats)
on the world shot with a slow push-in; the board plays the reel in place of the still. Untimed elements are the HUD at
rest. `check` warns when a moment is still a still.

**A blind critique before the owner sees it** (`kit ui direct critique <name>`, then `--record <answers.json> --judge
"<who>"`): a FRESH reviewer gets the directions numbered in a random order — no titles, no recommendation — and ranks
them by originality, names each one's cliché, what they would remember tomorrow and one stronger version. It lands on the
board under each direction and in `learn`'s "what blind critics keep naming". Act on it (a round 2), critique again,
THEN show the owner. What the first round taught: a centre-screen stamp / card is the expected move — transform the
direction's OWN object (the talisman ignites and grows back) or let the WORLD carry the moment (the kill as footage on
the crossing's own screen).

**After the pick** (`kit ui direct sources <name> [<key>]`): the picked direction's sources become the exact gather
commands — a game's own store screens (`kit ui refs <id> "<game>" "<words>"`), everything else as freely licensed
stills from Wikimedia Commons (`--wiki commons.wikimedia.org`); downloads run with the owner's go-ahead. Then the
hero route from stage 1, the identity's tokens measured from those stills.

Reels are written on ONE octree palette built from frames across the moment (a per-frame median cut greyed out
Fulgurite's green shards); the board opens with a cover grid of every moment's strip.

**Does the moment SHOW?** Every reel reports `visible`: the largest share of the frame its moment changes (pixels
moving more than 40 levels from the first frame). Under 4% warns - a blind critic's "almost nothing happens" in a number
(SampleDunes's first Gold Seams / Shadow Hour moments were 2-3%; a corner bar's quench was invisible until it grew).

**One judge is noisy**: the Veil went last, 2nd, last over three single-judge rounds. Record several judges per round
with one label (`--round 4`): `movement` averages each round's judges and says when a round stands on one judge.

## The lock
A screen whose identity was made after 2026-10-24 compiles only when that identity's `direction` names a checked
brief the owner PICKED (`kit/ui/refs_lock.py`, before the refs lock). Identities made before it are listed in
`kit/ui/direct_exempt.json` (frozen). The owner can waive it: `kit approve ui <identity> "<words>" --by owner --waive direction`.

## The first run (SampleCity, 2026-10-24)
Ask (a test prompt in the owner's register): "make a sick hud for neon crossing, like jjk shibuya but original, AAA not
ai slop" → A Last Train Out (the station's wayfinding: line roundels, departure board, exit plates; Service Suspended),
B The Veil (talismans burning, a vermilion seal; Black Flash), C Cursed Broadcast (the crossing's video walls hijacked;
Breaking News), D Infinite Void (diegetic light rings; the information flood). Brief:
games/SampleCity/assets/ui/directions/neon-hud.json; board: build/ui/directions/SampleCity/neon-hud/.
