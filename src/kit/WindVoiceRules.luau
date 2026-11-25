--!strict
-- WindVoiceRules.luau — a castle that SINGS in the wind (pure, tested). Wind across battlements and arrow slits
-- excites tonal whistles (aeolian tones); the kit plays one tonal loop per voice point and these rules decide how it
-- moves: louder with the wind speed (silent-ish in calm air, full in a gale), louder where the wind grazes across an
-- opening's mouth, a hair of pitch drift with the level (the castle keeps its key), and only the nearest voices sound (a cap).
-- The world's wind is the one Workspace.GlobalWind the WorldClock blows, so the voice swells with the grass and the
-- ambience gusts. Data: the "voices" block `kit sfx ambience <World>` writes from the blueprint's towers and walls.
local WindVoiceRules = {}

local function num(v: unknown, default: number): number
	return if type(v) == "number" and v == v then v else default
end

-- 0..1: how hard the castle sings at this wind speed (studs/s). Below `calm` only a breath (`floor`); a smooth rise
-- to full at `full` (an aeolian tone needs flow to lock in, then saturates).
function WindVoiceRules.level(speed: number, spec: any?): number
	local s = if type(spec) == "table" then spec else {}
	local calm, full, floor = num(s.calm, 3), num(s.full, 14), num(s.floor, 0.08)
	if full <= calm then
		full = calm + 1
	end
	local t = math.clamp((num(speed, 0) - calm) / (full - calm), 0, 1)
	t = t * t * (3 - 2 * t)
	return floor + (1 - floor) * t ^ 1.5
end

-- 0.35..1: an opening (a slit, a crenel: a CAVITY, face normal nx, nz) sings hardest when the wind grazes ACROSS its
-- mouth - blowing across a bottle - and least when the wind blows straight into it. (A cavity's pitch is set by its
-- size, not the wind speed: that is why the castle keeps its key.)
function WindVoiceRules.exposure(wx: number, wz: number, nx: number, nz: number): number
	local wl, nl = math.sqrt(wx * wx + wz * wz), math.sqrt(nx * nx + nz * nz)
	if wl < 1e-6 or nl < 1e-6 then
		return 0.35
	end
	return 0.35 + 0.65 * (1 - math.abs((wx * nx + wz * nz) / (wl * nl)))
end

-- the loop's playback speed: +-0.75 % with the level (life, not a key change)
function WindVoiceRules.pitch(level: number): number
	return 1 + 0.015 * (math.clamp(level, 0, 1) - 0.5)
end

-- a voice's target volume
function WindVoiceRules.volume(level: number, exposure: number, spec: any?): number
	local s = if type(spec) == "table" then spec else {}
	return math.clamp(num(s.volume, 0.6) * level * exposure, 0, 1)
end

-- which voice points sound: the nearest `max` within `range` of the listener (x, z); indices, nearest first
function WindVoiceRules.pick(points: { any }, x: number, z: number, max: number?, range: number?): { number }
	local lim, r = num(max, 6), num(range, 260)
	local cand = {}
	for i, p in points do
		if type(p) == "table" then
			local d = math.sqrt((num(p.x, 0) - x) ^ 2 + (num(p.z, 0) - z) ^ 2)
			if d <= r then
				table.insert(cand, { i = i, d = d })
			end
		end
	end
	table.sort(cand, function(a, b)
		return a.d < b.d
	end)
	local out = {}
	for k = 1, math.min(#cand, math.max(0, math.floor(lim))) do
		out[k] = cand[k].i
	end
	return out
end

return WindVoiceRules
