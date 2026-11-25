-- Guard.luau — validate UNTRUSTED values arriving from the client (RemoteEvent/RemoteFunction args).
-- Pure (no game APIs). Every function returns (ok, valueOrReason). Typical server use:
--   local ok, amount = Guard.number(rawAmount, 1, 100); if not ok then return end
-- Never trust the client: check type, finiteness, range, and length for EVERY argument.
local Guard = {}

local function finite(n: number): boolean
	return n == n and n ~= math.huge and n ~= -math.huge
end

function Guard.number(v: unknown, min: number, max: number): (boolean, any)
	if type(v) ~= "number" or not finite(v) then
		return false, "not a finite number"
	end
	if not (v >= min and v <= max) then -- (written so a NaN bound refuses: `v < NaN` is false for every v)
		return false, `out of range {min}..{max}`
	end
	return true, v
end

function Guard.integer(v: unknown, min: number, max: number): (boolean, any)
	local ok, n = Guard.number(v, min, max)
	if not ok then
		return false, n
	end
	if n % 1 ~= 0 then
		return false, "not a whole number"
	end
	return true, n
end

function Guard.string(v: unknown, maxLen: number): (boolean, any)
	if type(v) ~= "string" then
		return false, "not a string"
	end
	if #v == 0 or #v > maxLen then
		return false, `length must be 1..{maxLen}`
	end
	return true, v
end

function Guard.oneOf(v: unknown, allowed: { string }): (boolean, any)
	for _, a in allowed do
		if v == a then
			return true, v
		end
	end
	return false, "not an allowed value"
end

function Guard.boolean(v: unknown): (boolean, any)
	if type(v) ~= "boolean" then
		return false, "not a boolean"
	end
	return true, v
end

-- Vector3 (Roblox only; typeof is "Vector3"). Rejects NaN/inf components — a classic exploit vector.
function Guard.vector3(v: unknown): (boolean, any)
	if typeof(v) ~= "Vector3" then
		return false, "not a Vector3"
	end
	local vec = v :: any
	if not (finite(vec.X) and finite(vec.Y) and finite(vec.Z)) then
		return false, "non-finite component"
	end
	return true, vec
end

-- Horizontal + vertical distance check used for "is the target within reach of the player".
function Guard.withinRange(
	from: { X: number, Y: number, Z: number },
	to: { X: number, Y: number, Z: number },
	max: number
): boolean
	local dx, dy, dz = to.X - from.X, to.Y - from.Y, to.Z - from.Z
	return dx * dx + dy * dy + dz * dz <= max * max
end

return Guard
