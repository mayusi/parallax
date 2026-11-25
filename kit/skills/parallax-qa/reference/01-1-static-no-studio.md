<!-- reference for the parallax-qa route card; verbatim from the skill page (2026-10-16) -->

## 1. Static (no Studio)
- `lune run kit audit` — every `OnServerEvent`/`OnServerInvoke` handler: each client argument must be validated
  (Guard / typeof / type / a check function) and the handler rate-limited. Also flags `require(<asset id>)`
  (free-model backdoor), `loadstring`, server `InvokeClient`, `getfenv/setfenv`, `FireAllClients` in loops.
  It runs inside `kit verify`. Accepted risk? Add `"file:line"` to `qa.auditIgnore` in kit.config.json + a note why.
- `lune run kit verify` — the full gate. `lune run kit selftest` — proves every gate still catches bad input.
