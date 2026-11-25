# __NAME__ — world brief

ASK THE OWNER before building; write the answers here. A world is judged at eye level and by how it plays.

## Source and look
- What is it from, or like? (the game / film / place — name the exact areas, screenshots or videos to study)
- The look in their words, and the 3 things a player must SEE first (the landmarks):
- Time of day, weather, mood:

## Play
- What happens here (arena, open region, lobby, dungeon, hub)? How many players?
- The routes: where players start, where they must go, what blocks them (cliffs, water, walls):
- Fights: open ground or cover? How far can you see (sightlines)?

## Scale and budget
- Size in studs (a 1024 x 1024 region is ~4 minutes to cross on foot at 16 studs/s):
- Devices (phones = keep under ~3,000 parts):

## Parts plan (how each piece gets made)
| Piece | Generator | Notes |
|---|---|---|
| the land | `kit world terrain --design` (rim / plateau / basin / hill / ridge / ramp) | |
| the horizon | `horizon` (distant ranges, backdrop) | |
| landmarks | `building` / `tower` / `ruin` / `arch` / `tree` (style `erd` for a colossus) | |
| roads | `path` + `"worn"` (a trail in the land) | |
| nature | `forest`, `rocks` (crags + spires), `scatter` | |
| light | `lighting` preset, `light` / `particles` on parts, `grace` | |
