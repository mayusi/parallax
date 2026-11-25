# __NAME__

The game's brief. ASK THE OWNER every TODO before building anything; `lune run kit game check` lists the ones left.
Decisions made later go in the log at the bottom (date, what, why) — never silently.

## Pitch
TODO: one or two sentences — what the player does and why it is fun.

## Genre and source
TODO: the genre, and the real games / anime / films it takes from. Every piece of this game gets its OWN look from
these sources at their quality (the originality rule): name the frames, screens and moments to study.

## Core loop
TODO: what the player does minute to minute, session to session (fight → loot → upgrade → ...).

## Pillars
TODO: three things every feature must serve (e.g. "every hit feels heavy", "readable at a glance on a phone").

## Players and devices
TODO: solo / co-op / PvP, server size, age, and devices (phone first? controller?).

## Places and worlds
TODO: every place (lobby, arena, open region, ...) — each becomes `assets/worlds/<Name>.json`.

## Systems
TODO: the gameplay systems (combat, abilities, inventory, quests, ...) — each becomes `kit new system <Name>`,
its remotes `assets/net/<System>.net.json`, its moves `assets/moves/`.

## Progression and economy
TODO: currencies, levels, unlocks, what is saved.

## Art direction
TODO: the UI identity (`assets/ui/identities/<name>.json`), palette, lighting mood, the 3D style.

## Audio direction
TODO: the sound identity (`assets/sounds/identities/<name>.json`), music mood.

## Monetisation
TODO: game passes / products, or none.

## Milestones
TODO: the first playable, then what comes after (each milestone = board tasks: `kit task new ...`).

## Decision log
- __DATE__ — the game's folder made (`kit game new __NAME__`).
