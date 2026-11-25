-- NEGATIVE fixture for `kit fuzz`: a rules function that THROWS on a NaN instead of answering. Never fix.
local Crashy = {}

function Crashy.check(power: number): (boolean, string?)
	assert(power == power, "power is NaN")
	return power >= 0 and power <= 1, nil
end

return Crashy
