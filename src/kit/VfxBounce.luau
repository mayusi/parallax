--!strict
-- VfxBounce (kit) — F1b: a swarm particle that BOUNCES on its floor throws a burst of its own (LIMITATIONS_FIXES_V4
-- §3.4 step 3: "F1b onBounce sub-emitter"), the rules pure: src/kit/VfxStage.luau (swarm) and the browser player
-- (kit/vfx/player/player.js, SwarmLayer) apply the same numbers; kit/test/spec/vfxbounce.spec.luau proves them.
--
-- A swarm layer's floor:  "floor": { "y": 0, "bounce": 0.4, "onBounce": {
--     "count": 1..12      sparks a bounce throws at most (a hard landing: all of them; a soft one: fewer, at least 1)
--     "min": 0..200       the landing speed (studs a second, straight down) under which a bounce throws nothing
--     "max": 1..200       sub-bursts the whole layer throws at most (a swarm of 150 bouncing balls is not 150 bursts)
--     "life": 0.05..2     a spark's life (s);  "speed": [lo, hi] studs a second, thrown up off the floor in a cone
--     "spread": 0..80     the cone's half-angle (degrees round the floor's up);  "size": 0.02..2;  "gravity": 0..200
--     "color": [r, g, b] } }
-- In the game the sub-burst is ONE ParticleEmitter's Emit(n) at the contact (an explicit burst: the engine throttles a
-- continuous Rate on low graphics settings, an Emit is kept).
local VfxBounce = {}

VfxBounce.KEYS = {
	count = true,
	min = true,
	max = true,
	life = true,
	speed = true,
	spread = true,
	size = true,
	gravity = true,
	color = true,
}

local function isNum(v: any, lo: number, hi: number): boolean
	return type(v) == "number" and v == v and v >= lo and v <= hi
end

-- checked(spec) -> (ok, problems): the onBounce block as the validator and both players read it
function VfxBounce.checked(s: any): (boolean, { string })
	local bad = {}
	if type(s) ~= "table" then
		return false, { "onBounce is a table { count, min, max, life, speed, spread, size, gravity, color }" }
	end
	for k in s do
		if not VfxBounce.KEYS[k] then
			table.insert(bad, `onBounce.{tostring(k)} is not a key it reads`)
		end
	end
	local function want(k: string, lo: number, hi: number, whole: boolean?)
		local v = s[k]
		if v ~= nil and (not isNum(v, lo, hi) or (whole and v ~= math.floor(v))) then
			table.insert(bad, `onBounce.{k} is {if whole then "a whole number" else "a number"} {lo}..{hi}`)
		end
	end
	want("count", 1, 12, true)
	want("min", 0, 200)
	want("max", 1, 200, true)
	want("life", 0.05, 2)
	want("spread", 0, 80)
	want("size", 0.02, 2)
	want("gravity", 0, 200)
	if
		s.speed ~= nil
		and not (
			type(s.speed) == "table"
			and #s.speed == 2
			and isNum(s.speed[1], 0, 200)
			and isNum(s.speed[2], 0, 200)
			and s.speed[1] <= s.speed[2]
		)
	then
		table.insert(bad, "onBounce.speed is [lo, hi], 0..200, lo <= hi")
	end
	if
		s.color ~= nil
		and not (
			type(s.color) == "table"
			and #s.color == 3
			and isNum(s.color[1], 0, 255)
			and isNum(s.color[2], 0, 255)
			and isNum(s.color[3], 0, 255)
		)
	then
		table.insert(bad, "onBounce.color is [r, g, b], 0..255")
	end
	return #bad == 0, bad
end

-- contact(y, vy, floorY, bounce) -> (bounced, y', vy', landing speed): the floor rule both players already used (the
-- speed along the floor is kept at 0.8 by the caller), plus the landing speed the sub-burst is sized by
function VfxBounce.contact(y: number, vy: number, floorY: number, bounce: number?): (boolean, number, number, number)
	if y >= floorY then
		return false, y, vy, 0
	end
	local land = math.max(-vy, 0)
	return true, floorY, -vy * (bounce or 0.4), land
end

-- burst(spec, landing speed, used) -> how many sparks this bounce throws (0: none - too soft, or the layer's max used)
function VfxBounce.burst(s: any, land: number, used: number): number
	if type(s) ~= "table" or type(land) ~= "number" or land ~= land then
		return 0
	end
	local min = s.min or 4
	local maxBursts = s.max or 24
	if land < min or used >= maxBursts then
		return 0
	end
	local count = s.count or 4
	-- a landing at three times the threshold throws them all; just over it, at least one
	local k = math.clamp(land / math.max(min * 3, 1e-3), 0, 1)
	return math.clamp(math.floor(count * k + 0.5), 1, count)
end

return VfxBounce
