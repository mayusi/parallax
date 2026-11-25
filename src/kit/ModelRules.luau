--!strict
-- ModelRules.luau — the pure rules of Models (no services, no instances: spec'd under lune, kit/test/spec/
-- modelrules.spec.luau). Two things:
--   1. WHICH collision shape and level of detail a spawned mesh asks Roblox for. The build chose them per mesh
--      (kit/blender/rbx_fidelity.py -> the manifest -> the model file's attributes); a part NOTHING can touch
--      (no collision, no raycast, no touch event: a Tool's parts) asks for the cheapest shape whatever the build
--      said. A part that only does not collide keeps its shape: raycasts still hit it.
--   3. WHAT a model's own motion is at a time (cycleAt) and which of its marks a step of time passed (marksPassed):
--      the table the build wrote for an action cycle (a.cycle; kit/blender/rbx_cycleplay.py) played back.
--   2. WHEN a mesh that failed to load is tried again. One failed web request used to mark the mesh as failed for
--      the whole session (every later spawn a grey stand-in; the owner's limitations page, D-R10): now it is
--      tried again after a pause, a few times, and only then given up.
local ModelRules = {}

ModelRules.COLLISION = { Box = true, Hull = true, Default = true, PreciseConvexDecomposition = true }
ModelRules.RENDER = { Automatic = true, Precise = true, Performance = true }
-- seconds to wait after the 1st, 2nd, 3rd failure of one mesh; a 4th failure gives it up for the session
ModelRules.RETRY = { 2, 8, 30 }

export type Failure = { fails: number, at: number }

-- the names one spawn asks for: (CollisionFidelity, RenderFidelity). Unknown or missing -> Roblox's defaults.
function ModelRules.fidelity(collision: any, render: any, ghost: boolean?): (string, string)
	local c = "Default"
	if ghost == true then
		c = "Box" -- nothing touches it: the cheapest shape
	elseif type(collision) == "string" and ModelRules.COLLISION[collision] then
		c = collision
	end
	local r = if type(render) == "string" and ModelRules.RENDER[render] then render else "Automatic"
	return c, r
end

-- A GROUP'S PHYSICS MATERIAL (a.physics in the build script -> the manifest -> the model file's attributes): what
-- Roblox's PhysicalProperties takes, held to the ranges the engine takes (density 0.01..100, friction 0..2,
-- elasticity 0..1). Missing numbers take Roblox's own defaults for a plain part. nil when none was said.
ModelRules.PHYSICS = { density = { 0.01, 100, 0.7 }, friction = { 0, 2, 0.3 }, elasticity = { 0, 1, 0.5 } }

function ModelRules.physics(density: any, friction: any, elasticity: any): (number?, number?, number?)
	if type(density) ~= "number" and type(friction) ~= "number" and type(elasticity) ~= "number" then
		return nil, nil, nil
	end
	local function held(v: any, range: { number }): number
		if type(v) ~= "number" or v ~= v then
			return range[3]
		end
		return math.clamp(v, range[1], range[2])
	end
	local p = ModelRules.PHYSICS
	return held(density, p.density), held(friction, p.friction), held(elasticity, p.elasticity)
end

-- THE FAR STAND-IN (a.far in the build script): Roblox's own - a model whose LevelOfDetail is StreamingMesh is
-- drawn as one coarse mesh while it is streamed out. The names Enum.ModelLevelOfDetail takes; else nil (left alone).
ModelRules.FAR = { Automatic = true, StreamingMesh = true, Disabled = true }

function ModelRules.far(name: any): string?
	return if type(name) == "string" and ModelRules.FAR[name] then name else nil
end

-- A PART BROKEN BEFOREHAND (a.fracture in the build script): the push a piece gets when the whole lets go - away
-- from the whole's centre, `speed` studs a second; a piece AT the centre goes straight up. Numbers in, numbers out.
function ModelRules.burst(
	cx: number,
	cy: number,
	cz: number,
	x: number,
	y: number,
	z: number,
	speed: number
): (number, number, number)
	local dx, dy, dz = x - cx, y - cy, z - cz
	local length = math.sqrt(dx * dx + dy * dy + dz * dz)
	if length < 1e-6 then
		return 0, speed, 0
	end
	local k = speed / length
	return dx * k, dy * k, dz * k
end

-- Roblox would not create the mesh WITH its settings but did without: how often before that is taken as its answer
-- for the session (once may be a web request that failed by chance)
ModelRules.REFUSALS = 2

-- one template per mesh AND per pair of settings (a MeshPart's shape is fixed when it is created)
function ModelRules.key(meshId: string, collision: string, render: string): string
	return meshId .. "|" .. collision .. "|" .. render
end

-- a load just failed at `now`: the mesh's new record
function ModelRules.failed(state: Failure?, now: number): Failure
	return { fails = (if state then state.fails else 0) + 1, at = now }
end

-- is this mesh given up for the session?
function ModelRules.givenUp(state: Failure?): boolean
	return state ~= nil and state.fails > #ModelRules.RETRY
end

-- may this mesh be tried now? -> (yes, seconds still to wait: 0 when yes, math.huge when given up)
function ModelRules.mayTry(state: Failure?, now: number): (boolean, number)
	if state == nil then
		return true, 0
	end
	if ModelRules.givenUp(state) then
		return false, math.huge
	end
	local left = ModelRules.RETRY[state.fails] - (now - state.at)
	if left <= 0 then
		return true, 0
	end
	return false, left
end

export type Cycle = {
	joints: { string },
	times: { number },
	values: { { number } },
	length: number,
	loop: boolean?,
	marks: { [string]: number }?,
}

-- where in the cycle a time is: looped, round again; else held at its two ends
function ModelRules.cycleTime(cycle: Cycle, seconds: number, loop: boolean?): number
	local length = cycle.length
	if loop and length > 0 then
		return seconds % length
	end
	return math.clamp(seconds, 0, length)
end

-- every joint's value at a time: a straight line between the two keys round it (rbx_cycleplay.at does the same
-- in the build: what plays is what was checked). -> { [joint name]: value }
function ModelRules.cycleAt(cycle: Cycle, seconds: number, loop: boolean?): { [string]: number }
	local times, values = cycle.times, cycle.values
	local s = ModelRules.cycleTime(cycle, seconds, loop)
	local n = #times
	local lo, hi, w = n, n, 0
	if s <= times[1] then
		lo, hi = 1, 1
	else
		for i = 1, n - 1 do
			if s <= times[i + 1] then
				local span = times[i + 1] - times[i]
				lo, hi, w = i, i + 1, if span > 0 then (s - times[i]) / span else 1
				break
			end
		end
	end
	local out: { [string]: number } = {}
	for j, name in cycle.joints do
		local a, b = values[lo][j], values[hi][j]
		out[name] = a + (b - a) * w
	end
	return out
end

-- the marks a step of time passed, in the order they fall: from just after `before` up to and including `now`
-- (seconds since the cycle began, not yet wrapped); a looped cycle passes its marks again each time round
function ModelRules.marksPassed(cycle: Cycle, before: number, now: number, loop: boolean?): { string }
	local found: { { name: string, at: number } } = {}
	local length = cycle.length
	local marks: { [string]: number } = cycle.marks or {}
	for name, at in marks do
		if loop and length > 0 then
			-- every time round k where k * length + at falls in (before, now]
			local k = math.max(0, math.ceil((before - at) / length))
			if k * length + at <= before then
				k += 1
			end
			while k * length + at <= now do
				table.insert(found, { name = name, at = k * length + at })
				k += 1
			end
		elseif at > before and at <= now then
			table.insert(found, { name = name, at = at })
		end
	end
	table.sort(found, function(a, b)
		if a.at ~= b.at then
			return a.at < b.at
		end
		return a.name < b.name
	end)
	local names = {}
	for _, f in found do
		table.insert(names, f.name)
	end
	return names
end

export type Step = { at: number, values: { [string]: number }, marks: { string }, done: boolean }

-- ONE STEP of a cycle being played: from `at` seconds on by dt * speed. -> where it stands now, every joint's value
-- there, the marks that step passed, and whether a cycle that does not loop has played through. The first step of
-- a play is playStep(cycle, nil, 0, ...): it stands at 0 and passes the marks at 0. A step never passes a mark
-- more than once: a step longer than the whole loop is taken as one round.
function ModelRules.playStep(cycle: Cycle, at: number?, dt: number, speed: number, loop: boolean?): Step
	local before = if at == nil then -1 else at
	local now = if at == nil then 0 else at + math.max(0, dt) * math.max(0, speed)
	if loop and cycle.length > 0 and at ~= nil and now - before > cycle.length then
		before = now - cycle.length
	end
	local done = not loop and now >= cycle.length
	return {
		at = now,
		values = ModelRules.cycleAt(cycle, now, loop),
		marks = ModelRules.marksPassed(cycle, before, now, loop),
		done = done,
	}
end

-- A CYCLE FADING IN (Models.play's fade): every joint from where it stood toward the new cycle's value, eased (a
-- part starts and stops, as a cycle's own keys do). w: 0 .. 1 of the fade. A joint the new cycle does not key goes
-- to rest (0), as it would stand in that cycle; one only the new cycle keys stands at its value. -> { [joint]: value }
function ModelRules.blend(from: { [string]: number }, to: { [string]: number }, w: number): { [string]: number }
	local e = math.clamp(w, 0, 1)
	e = e * e * (3 - 2 * e)
	local out: { [string]: number } = {}
	for name, b in to do
		local a = from[name]
		out[name] = if a == nil then b else a + (b - a) * e
	end
	for name, a in from do
		if out[name] == nil then
			out[name] = a * (1 - e)
		end
	end
	return out
end

-- A MODEL'S OWN RIG, SOLVED (a.reach in the build script; the build's twin: kit/blender/rbx_ik.py - the same
-- steps). A chain is joints from its base outward, each { kind = "hinge" | "slide", pivot = {x, y, z},
-- axis = {x, y, z}, min, max } in the model's REST pose; tip is the point the last joint carries, at rest.
export type Link = { kind: string, pivot: { number }, axis: { number }, min: number, max: number }

local function turned(ax: number, ay: number, az: number, deg: number, x: number, y: number, z: number)
	local t = math.rad(deg)
	local c, s = math.cos(t), math.sin(t)
	local d = ax * x + ay * y + az * z
	local cx, cy, cz = ay * z - az * y, az * x - ax * z, ax * y - ay * x
	return x * c + cx * s + ax * d * (1 - c), y * c + cy * s + ay * d * (1 - c), z * c + cz * s + az * d * (1 - c)
end

-- where a chain's tip is with its joints at `values` -> x, y, z, and each joint's pivot and axis as posed
function ModelRules.chainTip(
	chain: { Link },
	values: { number },
	tip: { number }
): (number, number, number, { { number } }, { { number } })
	local n = #chain
	local piv: { { number } }, axs: { { number } } = {}, {}
	for i, j in chain do
		piv[i] = { j.pivot[1], j.pivot[2], j.pivot[3] }
		local a = j.axis
		local l = math.max(math.sqrt(a[1] * a[1] + a[2] * a[2] + a[3] * a[3]), 1e-30)
		axs[i] = { a[1] / l, a[2] / l, a[3] / l }
	end
	local tx, ty, tz = tip[1], tip[2], tip[3]
	for i = 1, n do
		local p, a, v = piv[i], axs[i], values[i] or 0
		local slide = chain[i].kind == "slide"
		local function point(x: number, y: number, z: number): (number, number, number)
			if slide then
				return x + a[1] * v, y + a[2] * v, z + a[3] * v
			end
			local rx, ry, rz = turned(a[1], a[2], a[3], v, x - p[1], y - p[2], z - p[3])
			return rx + p[1], ry + p[2], rz + p[3]
		end
		for k = i + 1, n do -- (a joint carries everything after it)
			piv[k][1], piv[k][2], piv[k][3] = point(piv[k][1], piv[k][2], piv[k][3])
			if not slide then
				axs[k][1], axs[k][2], axs[k][3] = turned(a[1], a[2], a[3], v, axs[k][1], axs[k][2], axs[k][3])
			end
		end
		tx, ty, tz = point(tx, ty, tz)
	end
	return tx, ty, tz, piv, axs
end

ModelRules.REACH_ROUNDS = 200 -- times round the chain at most, from one start
ModelRules.REACH_NEAR = 1e-3 -- studs: the tip is THERE
ModelRules.REACH_MET = 0.02 -- studs: near enough to stop looking for a better start
ModelRules.REACH_STARTS = 12 -- fresh starts tried when the first does not get there (rbx_ik.STARTS: the same ones)

-- one start, run down: round the chain from the tip back until the tip is there or has stopped moving
local function descend(chain: { Link }, tip: { number }, target: { number }, values: { number }): number
	local n = #chain
	local function missOf(): number
		local x, y, z = ModelRules.chainTip(chain, values, tip)
		local dx, dy, dz = target[1] - x, target[2] - y, target[3] - z
		return math.sqrt(dx * dx + dy * dy + dz * dz)
	end
	local miss = missOf()
	for _ = 1, ModelRules.REACH_ROUNDS do
		for i = n, 1, -1 do
			local x, y, z, piv, axs = ModelRules.chainTip(chain, values, tip)
			local p, a = piv[i], axs[i]
			local step = 0
			if chain[i].kind == "slide" then
				step = (target[1] - x) * a[1] + (target[2] - y) * a[2] + (target[3] - z) * a[3]
			else
				-- the tip and the target, seen along the joint's own axis
				local ux, uy, uz = x - p[1], y - p[2], z - p[3]
				local du = ux * a[1] + uy * a[2] + uz * a[3]
				ux, uy, uz = ux - a[1] * du, uy - a[2] * du, uz - a[3] * du
				local wx, wy, wz = target[1] - p[1], target[2] - p[2], target[3] - p[3]
				local dw = wx * a[1] + wy * a[2] + wz * a[3]
				wx, wy, wz = wx - a[1] * dw, wy - a[2] * dw, wz - a[3] * dw
				local lu, lw = math.sqrt(ux * ux + uy * uy + uz * uz), math.sqrt(wx * wx + wy * wy + wz * wz)
				if lu > 1e-9 and lw > 1e-9 then
					local cx, cy, cz = uy * wz - uz * wy, uz * wx - ux * wz, ux * wy - uy * wx
					step = math.deg(math.atan2(cx * a[1] + cy * a[2] + cz * a[3], ux * wx + uy * wy + uz * wz))
				end
			end
			local j = chain[i]
			values[i] = math.clamp(values[i] + step, math.min(j.min, j.max), math.max(j.min, j.max))
		end
		local now = missOf()
		local still = math.abs(miss - now) < 1e-7
		miss = now
		if now < ModelRules.REACH_NEAR or still then
			break
		end
	end
	return miss
end

-- the joint values that put the chain's tip nearest the target (cyclic coordinate descent: joint by joint from the
-- tip back, each turned or slid to bring the tip nearest, held to its limits; when the first start does not get
-- there, fresh starts are tried - the same ones the build tries - and the best kept) -> values, the studs it
-- misses by. `start`: the values to begin from (a game passes the chain's present pose: the arm does not jump).
function ModelRules.reach(
	chain: { Link },
	tip: { number },
	target: { number },
	start: { number }?
): ({ number }, number)
	local n = #chain
	local function held(i: number, v: number): number
		local j = chain[i]
		return math.clamp(v, math.min(j.min, j.max), math.max(j.min, j.max))
	end
	local first: { number } = {}
	for i = 1, n do
		first[i] = held(i, if start and start[i] then start[i] else 0)
	end
	local best, bestMiss = first, descend(chain, tip, target, first)
	local seed = 20261115
	for _ = 1, ModelRules.REACH_STARTS do
		if bestMiss <= ModelRules.REACH_MET then
			break
		end
		local values: { number } = {}
		for i, j in chain do
			seed = (seed * 16807) % 2147483647
			local lo, hi = math.min(j.min, j.max), math.max(j.min, j.max)
			values[i] = lo + (hi - lo) * (seed / 2147483647)
		end
		local miss = descend(chain, tip, target, values)
		if miss < bestMiss then
			best, bestMiss = values, miss
		end
	end
	return best, bestMiss
end

-- a joint that FOLLOWS another (a.couple): its value for the driver's
function ModelRules.follow(driver: number, ratio: any, offset: any): number
	return (if type(ratio) == "number" then ratio else 1) * driver + (if type(offset) == "number" then offset else 0)
end

return ModelRules
