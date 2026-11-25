-- __NAME__Rules.luau — the decisions of the __NAME__ system as PURE functions (unit-tested in tests/spec).
-- Put every rule the server enforces here, so it is tested without Studio. String requires work in both Lune
-- and Roblox: siblings "./X", kit runtime "../kit/X". Never use script.Parent in shared modules.
local Guard = require("../kit/Guard")
local __NAME__Config = require("./__NAME__Config")

local __NAME__Rules = {}

-- power comes from the client (untrusted); distance is computed by the server.
-- Even server-made numbers get checked: a NaN / nil here would slip past a plain `>` (kit fuzz proves it).
function __NAME__Rules.check(power: unknown, distance: unknown): (boolean, string?)
	local ok, reason = Guard.number(power, 1, __NAME__Config.MAX_POWER)
	if not ok then
		return false, `power {reason}`
	end
	if type(distance) ~= "number" or distance ~= distance or distance > __NAME__Config.RANGE then
		return false, "target out of range"
	end
	return true, nil
end

return __NAME__Rules
