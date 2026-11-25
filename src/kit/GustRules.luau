--!strict
-- GustRules.luau — rare moments the WIND causes (pure, tested): a drowned bell knocked when a gust moves the lake,
-- a banner snapping, a shutter banging. Not a timer: an event fires only on a real gust - the world's wind speed
-- (Workspace.GlobalWind, blown by the WorldClock) rising well above its own recent average - then rests for its
-- cooldown, and only fires with its chance, so it stays rare and tied to what the player can see the wind doing.
local GustRules = {}

local function num(v: unknown, default: number): number
	return if type(v) == "number" and v == v then v else default
end

-- a fresh tracker: the wind's slow average (an exponential mean over `window` seconds) and each rule's last fire
function GustRules.new(): { mean: number?, last: { [number]: number }, above: { [number]: boolean } }
	return { mean = nil, last = {}, above = {} }
end

-- advance the wind's running mean by dt seconds; returns the new mean
function GustRules.track(state: any, speed: number, dt: number, window: number?): number
	local w = math.max(1, num(window, 20))
	if state.mean == nil then
		state.mean = speed
	else
		local k = 1 - math.exp(-math.max(0, dt) / w)
		state.mean += (speed - state.mean) * k
	end
	return state.mean
end

-- does rule i fire now? A gust is speed >= mean * rise (default 1.3) and >= the rule's floor speed; it fires on the
-- RISING edge only (one gust, one knock), past its cooldown, with its chance (roll 0..1)
function GustRules.fires(state: any, i: number, rule: any, speed: number, now: number, roll: number): boolean
	local mean = state.mean or speed
	local gust = speed >= mean * num(rule.rise, 1.3) and speed >= num(rule.floor, 4)
	local rising = gust and not state.above[i]
	state.above[i] = gust
	if not rising then
		return false
	end
	local last = state.last[i]
	if last and now - last < num(rule.cooldown, 90) then
		return false
	end
	if roll >= num(rule.chance, 0.5) then
		return false
	end
	state.last[i] = now
	return true
end

return GustRules
