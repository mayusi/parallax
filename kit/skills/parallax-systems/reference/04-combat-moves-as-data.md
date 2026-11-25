<!-- reference for the parallax-systems route card; verbatim from the skill page (2026-10-16) -->

## Combat: moves as data
`assets/moves/<Move>.json`: `anim`, `frames` (or `"from_anim"`: startup / active / recovery from the anim lane's
MEASURED phases, active widened to 3 frames), `hitboxes` per frame (size, offset), damage, stun, knockback [right, up,
forward], hitstop, blockstun, `block` (blockable / chip / unblockable), parryable, `cancel` { into, from, to },
`sfx` / `vfx` cues by frame, `onHit`. A set: `assets/moves/sets/<Set>.json` (`moves`, `combo`, `health`).
`kit move` validates (ghost hitboxes outside active frames, huge boxes, combo links that are not cancels), measures
on-block advantage + combo damage + time-to-kill, writes `src/moves/<Set>.json` (`ReplicatedStorage.KitMoves`) and a
MOVE SHEET `build/moves/<Set>.png` — look at it. In game: `Moves.serve("<Set>")` (server: cancels, combo scaling,
per-frame `GetPartBoundsInBox` hitboxes on the server's own positions, hit / block / chip / parry / i-frame dodge,
damage, stun, knockback, hit-stop, Sfx / Vfx from the data; NPCs: `.use(character, move)`; `Moves.debug(true)`) and
`Moves.client("<Set>").use / block / parry`.
