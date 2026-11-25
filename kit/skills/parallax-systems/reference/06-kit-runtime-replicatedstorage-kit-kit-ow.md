<!-- reference for the parallax-systems route card; verbatim from the skill page (2026-10-16) -->

## Kit runtime (ReplicatedStorage.kit, kit-owned — don't edit)
Guard · RateLimit · Loader · Configs · Moves / MovesRules · Sfx / SfxRules · Vfx · Anim · Ui · Assets · Environment.
**Bus** (the presentation event bus): gameplay says WHAT happened, presentation subscribes — server
`Bus.publish("Hit", {..., at = pos}, { near = 250 })`, client `Bus.start()` once then `Bus.on("Hit", fn)`; listeners
are isolated (one that errors never stops the rest), clients can never publish. `Moves` publishes Hit / Blocked /
Chip / Parried / Death (payload: attacker, victim, damage, move, at, weight, surface). **Recorder** (the flight
recorder): the last 64 remote calls, written out on any server error; `kit net` records every call for you.
`src/shared` is pure (no `game:GetService`, no `Instance.new`); siblings via `require("./X")`. Strict mode, stylua +
selene clean, `task.wait/delay/spawn`. Per-player tables cleared on `PlayerRemoving`.
