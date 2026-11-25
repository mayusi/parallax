-- __NAME__Config.luau — tuning for the __NAME__ system (a generic speed-burst / time-dilation mode: you move
-- fast, the world looks slowed on your screen, an afterimage trail follows you). Pure data: tests + both sides read it.
local __NAME__Config = {}

__NAME__Config.ENABLED = true
__NAME__Config.KEY = "Q" -- client keybind (Enum.KeyCode name)
__NAME__Config.DURATION = 6 -- seconds the mode lasts
__NAME__Config.COOLDOWN = 12 -- seconds after it ends before it can be used again
__NAME__Config.SPEED_MULTIPLIER = 1.8 -- WalkSpeed x this while active (server-applied)
__NAME__Config.WORLD_SLOW = 0.35 -- on the owner's screen, other characters' animations play at this speed
__NAME__Config.VFX = "time_surge" -- attach preset in assets/effects (afterimages + owner-only grade)
__NAME__Config.SOUND_ON = "powerup" -- kit sound played at activation (assets/sounds)
__NAME__Config.BURST = 2 -- requests allowed back-to-back (spam protection; cooldown is the real limit)
__NAME__Config.REFILL_PER_SECOND = 0.5
__NAME__Config.REQUEST = "__NAME__Request" -- client -> server RemoteEvent (no arguments)
__NAME__Config.ATTRIBUTE = "__NAME__Active" -- player attribute the server sets: every client (and late joiners) reads it

return __NAME__Config
