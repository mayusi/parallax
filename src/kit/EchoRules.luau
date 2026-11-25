--!strict
-- EchoRules.luau — places that ANSWER the player (pure, tested): inside an echo zone every sound the player makes
-- comes back from a point deeper in, `delay` seconds later (later than a true echo would: the catacomb's idea),
-- quieter, a shade lower, darker; and when the player stops after walking there, one more step may come back that
-- they never took (the phantom), once per stop, with its chance.
local EchoRules = {}

local function num(v: unknown, default: number): number
	return if type(v) == "number" and v == v then v else default
end

-- the echo zone (x, z, r: a circle on the ground; optional y range) the point is in, or nil
function EchoRules.zoneAt(zones: { any }?, x: number, y: number, z: number): any?
	if type(zones) ~= "table" then
		return nil
	end
	for _, zn in zones do
		if type(zn) == "table" then
			local dx, dz = x - num(zn.x, 0), z - num(zn.z, 0)
			local inY = (zn.y0 == nil or y >= num(zn.y0, -1e9)) and (zn.y1 == nil or y <= num(zn.y1, 1e9))
			if dx * dx + dz * dz <= num(zn.r, 0) ^ 2 and inY then
				return zn
			end
		end
	end
	return nil
end

-- how one sound comes back from a zone: { delay, volume factor, playback speed, deep point (x, y, z) }
function EchoRules.repeatOf(zn: any): { delay: number, volume: number, speed: number, at: { number } }
	local deep = if type(zn.deep) == "table" then zn.deep else { num(zn.x, 0), 0, num(zn.z, 0) }
	return {
		delay = math.clamp(num(zn.delay, 0.6), 0.05, 5),
		volume = 10 ^ (math.clamp(num(zn.gain_db, -9), -60, 6) / 20),
		speed = math.clamp(num(zn.pitch, 0.94), 0.5, 1.5),
		at = { num(deep[1], 0), num(deep[2], 0), num(deep[3], 0) },
	}
end

-- a step tracker for the phantom: call `step` on every real step in a zone, `due` every tick
function EchoRules.new(): { steps: number, last: number, spent: boolean, sound: string? }
	return { steps = 0, last = -1e9, spent = true, sound = nil }
end

function EchoRules.step(state: any, now: number, sound: string)
	state.steps += 1
	state.last = now
	state.spent = false
	state.sound = sound
end

-- the phantom step: once, `after` seconds after the player stopped, if they walked >= `min_steps` there, with `phantom`
-- chance (roll 0..1). Returns the sound to play, or nil. A new walk re-arms it.
function EchoRules.due(state: any, zn: any, now: number, roll: number): string?
	if state.spent or state.steps < num(zn.min_steps, 4) then
		return nil
	end
	local wait = num(zn.delay, 0.6) + num(zn.after, 0.65)
	if now - state.last < wait then
		return nil
	end
	state.spent = true
	state.steps = 0
	if roll >= num(zn.phantom, 0) then
		return nil
	end
	return state.sound
end

-- the REVERB of the place a listener stands in (LIMITATIONS_FIXES_V4 SFX-X 7.3: AudioReverb per zone): the "reverb"
-- name of the zone the point is in (an echo zone may set one: "HallStone", "CatacombCave", "CourtyardOpen"), else nil =
-- dry. A zone with no reverb named is dry too (its echo is the answer, not a room tail).
function EchoRules.reverbAt(zones: { any }?, x: number, y: number, z: number): string?
	local zn = EchoRules.zoneAt(zones, x, y, z)
	if zn and type(zn.reverb) == "string" and zn.reverb ~= "" then
		return zn.reverb
	end
	return nil
end

-- whether the reverb should change now: a new name, and the last change at least `hold` seconds ago (a listener on a
-- zone's edge must not flap the reverb every frame)
function EchoRules.reverbSwitch(
	current: string?,
	wanted: string?,
	now: number,
	lastChange: number,
	hold: number?
): boolean
	if current == wanted then
		return false
	end
	return now - lastChange >= num(hold, 0.5)
end

return EchoRules
