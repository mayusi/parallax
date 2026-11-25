<!-- reference for the parallax-anim route card; verbatim from the skill page (2026-10-16) -->

## Locomotion in a game (the kit's runtime blender)
Roblox Animation Graphs cannot be written by tooling (their node settings are opaque), so the kit blends clips
itself: `local loco = Anim.locomotion(character, { idle = "Idle", walk = "Walk", run = "Run", jump = "Jump",
fall = "Fall", land = "Land" })` (optional `back`, `strafeLeft`, `strafeRight`). Every frame
`AnimBlend.weights` (src/kit/AnimBlend.luau, pure, spec-tested) turns the move direction and speed into weights that
sum to 1 and a RATE per clip = speed / the clip's measured ground speed (ReplicatedStorage.KitAnimations.Meta,
written by `kit anim`), so the planted foot moves back at the character's real speed at any WalkSpeed. Jumping and
Landed play the set's one-shots (loaded once), Freefall holds the fall loop; a set missing a clip plays what it has
at full weight (no back clip: the walk plays in REVERSE so the planted foot still moves the right way — a clip asked
for twice blends its signed rates by weight, so a mostly-backward diagonal stays in reverse; `idle` is required). `loco:stop()` hands the character back to Roblox's Animate script — automatic when the character dies or
is removed. Call it on the client for the local player (animations replicate), on the server for NPCs.
