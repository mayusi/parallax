<!-- reference for the parallax-systems route card; verbatim from the skill page (2026-10-16) -->

## Server request order (the audit enforces it)
enabled → `limit:take(player.UserId, os.clock())` → `Guard.*` on EVERY client argument → `Rules.check(...)` → act →
reply. A malformed packet returns silently. Never trust client positions, damage, prices or ownership.
