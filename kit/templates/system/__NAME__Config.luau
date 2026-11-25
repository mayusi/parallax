-- __NAME__Config.luau — tuning for the __NAME__ system. Pure data (no game APIs): tests + both sides read it.
local __NAME__Config = {}

__NAME__Config.ENABLED = true
__NAME__Config.KEY = "F" -- client keybind (Enum.KeyCode name)
__NAME__Config.RANGE = 60 -- studs from the player's root the target may be
__NAME__Config.MAX_POWER = 10
__NAME__Config.BURST = 2 -- requests allowed back-to-back
__NAME__Config.REFILL_PER_SECOND = 0.5 -- then 1 request every 2 s
__NAME__Config.VFX = "hit_sparks" -- preset in assets/effects
__NAME__Config.REQUEST = "__NAME__Request" -- client -> server RemoteEvent
__NAME__Config.REPLY = "__NAME__Reply" -- server -> client RemoteEvent

return __NAME__Config
