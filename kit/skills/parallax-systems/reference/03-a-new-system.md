<!-- reference for the parallax-systems route card; verbatim from the skill page (2026-10-16) -->

## A new system
1. `kit new system <Pascal>` → Config + Rules (pure) + Service + Controller + spec.
2. Every DECISION in `<Name>Rules` + a spec case (hostile input too) → `kit fuzz <Name>Rules` (a throw = a crash;
   saying yes to NaN / inf / a wrong type = a warning) → `kit mutate <Name>Rules` (planted bugs your specs miss).
3. **Remotes from a schema**: `assets/net/<System>.net.json` → `kit net` → `src/net/<System>Net.luau`
   (`ReplicatedStorage.Net`). Server: `Net.Request.on(function(player, target: Vector3, power: number) ... end)` — the
   generated wrapper rate-limits per player and Guard-checks EVERY argument before your handler runs; client:
   `Net.Request.fire(...)`. The schema refuses an unbounded client number, an unlimited string, a vector3 with no
   magnitude cap, a request with no rate. `kit verify` fails if a generated file is edited or stale.
4. The EFFECT in the Service; the Controller only gathers input and shows feedback.
5. `kit verify` (the security audit runs inside it); a playtest (`kit new playtest`) — it FAILS on any script error in
   the console, named with its line.
