-- POSITIVE twin of Crashy: answers every hostile input with false + a reason (kit fuzz must pass it).
local Sturdy = {}

function Sturdy.check(power: unknown): (boolean, string?)
	if type(power) ~= "number" or power ~= power or math.abs(power) == math.huge then
		return false, "bad power"
	end
	return power >= 0 and power <= 1, nil
end

return Sturdy
