--!strict
-- VfxVictim (kit) — the RULES of how a hit victim reacts on screen (LIMITATIONS_FIXES_V4 §3.4 step 3 / §13.3.4: F2
-- "VfxImpact.onVictimHit(victimModel, hitCFrame, cutNormal, power): a pooled VfxHighlight rim flash, sparks along the
-- cut normal, a hitstop tremor"), pure: numbers in, numbers out (src/kit/VfxImpact.luau turns them into the engine's
-- Highlight, ParticleEmitter and joint offsets; kit/test/spec/vfxvictim.spec.luau proves them).
--
-- NO BLOOD, EVER (Roblox moderates the account that uploads blood or gore): a victim's
-- reaction is LIGHT - a white rim flash and sparks. A spark colour that reads as blood (red over green and blue,
-- or a dark red) is never drawn: it is swapped for the default spark colour, and said.
local VfxVictim = {}

VfxVictim.SPARK = { 255, 236, 190 } -- warm white sparks (the default)
VfxVictim.FLASH = { 255, 255, 255 } -- the rim flash
VfxVictim.MAX_SPARKS = 40
VfxVictim.MAX_POWER = 10

local function num(v: any, lo: number, hi: number, fallback: number): number
	if type(v) ~= "number" or v ~= v then
		return fallback
	end
	return math.clamp(v, lo, hi)
end

-- power 0..10 (anything else: 1) -> how hard the hit reads
function VfxVictim.power(p: any): number
	return num(p, 0, VfxVictim.MAX_POWER, 1)
end

-- is this colour (0..255 rgb) one that reads as blood? Red leading green and blue by far, or any dark red
function VfxVictim.isBloodRed(c: any): boolean
	if type(c) ~= "table" then
		return false
	end
	local r, g, b = num(c[1], 0, 255, 0), num(c[2], 0, 255, 0), num(c[3], 0, 255, 0)
	if r < 40 then
		return false
	end
	local other = math.max(g, b)
	return r >= 1.6 * other + 10 or (r >= 90 and r <= 200 and other <= r * 0.45)
end

-- the spark colour to draw (rgb 0..255) and whether the asked one was refused as blood
function VfxVictim.sparkColor(c: any): ({ number }, boolean)
	if type(c) ~= "table" or #c ~= 3 then
		return table.clone(VfxVictim.SPARK), false
	end
	if VfxVictim.isBloodRed(c) then
		return table.clone(VfxVictim.SPARK), true
	end
	return { num(c[1], 0, 255, 255), num(c[2], 0, 255, 255), num(c[3], 0, 255, 255) }, false
end

-- how many sparks a hit of this power throws (a whisper of a hit: a few; a finisher: the cap)
function VfxVictim.sparkCount(power: any): number
	local p = VfxVictim.power(power)
	return math.clamp(math.floor(4 + p * 3.6 + 0.5), 0, VfxVictim.MAX_SPARKS)
end

-- the direction sparks fly: the cut's normal made a unit vector; a zero / NaN normal -> the fallback (up)
function VfxVictim.sparkDirection(n: any): { number }
	if type(n) ~= "table" then
		return { 0, 1, 0 }
	end
	local x, y, z = num(n[1], -1e6, 1e6, 0), num(n[2], -1e6, 1e6, 0), num(n[3], -1e6, 1e6, 0)
	local m = math.sqrt(x * x + y * y + z * z)
	if m < 1e-6 then
		return { 0, 1, 0 }
	end
	return { x / m, y / m, z / m }
end

-- the rim flash: how long (60 fps frames) and the fill's transparency over those frames (0 = solid white)
function VfxVictim.flash(power: any): { number }
	local p = VfxVictim.power(power)
	local frames = math.clamp(math.floor(3 + p * 0.8 + 0.5), 2, 12)
	local out = {}
	for f = 1, frames do
		-- a hard first frame (solid), then fading: the anime white-out of a struck body
		table.insert(out, if f == 1 then 0 else math.clamp(0.25 + 0.75 * (f - 1) / (frames - 1), 0, 1))
	end
	return out
end

-- the hitstop tremor: per 60 fps frame of the hitstop, the victim's sideways offset in studs - alternating sides each
-- frame (the anime hit-shake), dying away, and zero on the last frame (it ends where it started)
function VfxVictim.tremor(frames: any, power: any): { number }
	local n = math.floor(num(frames, 0, 30, 0))
	local p = VfxVictim.power(power)
	local amp = 0.06 + 0.035 * p
	local out = {}
	for f = 1, n do
		if f == n then
			table.insert(out, 0)
		else
			local fade = 1 - (f - 1) / math.max(n - 1, 1)
			table.insert(out, (if f % 2 == 1 then 1 else -1) * amp * fade)
		end
	end
	return out
end

return VfxVictim
