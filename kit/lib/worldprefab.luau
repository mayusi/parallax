-- worldprefab.luau (kit) — A GROUP OF STEPS NAMED ONCE AND SET DOWN MANY TIMES (the owner's method list:
-- "Prefab-based assembly", "Hierarchical instancing"). A blueprint names a prefab - a market stall, a guard post, a
-- camp - as a list of ordinary build steps typed round the origin:
--   "prefabs": { "Stall": [ { "part": { ... "pos": [0, 2, 0] } }, { "part": { ... } } ],
--                "Market": [ { "prefab": { "name": "Stall", "at": [-10, 0, 0] } },
--                            { "prefab": { "name": "Stall", "at": [10, 0, 0], "turn": 180 } } ] }
-- and a build step sets it down:
--   { "prefab": { "name": "Market", "at": [120, 0, 40], "turn": 90, "as": "NorthMarket" } }
-- "at" is where the prefab's origin lands; "turn" turns the whole of it about that point (degrees, as a step's
-- own "turn"); "as" names this placement (else <name>_<n>). A prefab may hold prefabs (to Prefab.DEPTH deep): a
-- market of stalls, a town quarter of markets.
-- HOW IT IS DONE: the prefab's steps are built as they are typed (round the origin), and what each one made - its
-- parts, its scale claims - is then MOVED: shifted to "at", turned about it; for a prefab inside a prefab, moved
-- again by the outer one. So a placed stall is the same stall: no generator has to know it was moved.
-- That is why only steps whose whole result is parts and claims may stand in a prefab (the kinds a "turn" is
-- followed by, and decal and spawn), and why none of them may say "ground": true (the land where it is TYPED is not
-- the land where it will stand).
-- Pure: no file reads, no game calls.
local Prefab = {}

Prefab.DEPTH = 4 -- prefabs inside prefabs, at most
Prefab.STEPS = 200 -- steps one prefab may hold
Prefab.MOST = 4000 -- steps all placements of a blueprint may come to

local function number(v: any): boolean
	return type(v) == "number" and v == v and v ~= math.huge and v ~= -math.huge
end

local function name(v: any): boolean
	return type(v) == "string" and string.match(v, "^[%w_]+$") ~= nil
end

local function copy(v: any): any
	if type(v) ~= "table" then
		return v
	end
	local out = {}
	for k, x in v do
		out[k] = copy(x)
	end
	return out
end

local function one(step: any): (string?, any)
	if type(step) ~= "table" then
		return nil, nil
	end
	local kind, spec = next(step)
	if type(kind) ~= "string" or next(step, kind) ~= nil then
		return nil, nil
	end
	return kind, spec
end

-- what is wrong with one placement ({ name, at, turn?, as? }), in words
function Prefab.placement(spec: any, prefabs: any): { string }
	local out: { string } = {}
	if type(spec) ~= "table" then
		return { 'prefab needs { "name": "<a prefab of this blueprint>", "at": [x, y, z] }' }
	end
	for k in spec do
		if k ~= "name" and k ~= "at" and k ~= "turn" and k ~= "as" then
			table.insert(out, `prefab: "{tostring(k)}" is not a word it knows (name, at, turn, as)`)
		end
	end
	if not name(spec.name) then
		table.insert(out, 'prefab: "name" is a prefab of this blueprint\'s "prefabs"')
	elseif type(prefabs) ~= "table" or prefabs[spec.name] == nil then
		table.insert(out, `prefab: no prefab "{spec.name}" in this blueprint's "prefabs"`)
	end
	local at = spec.at
	local far = false
	if type(at) == "table" and #at == 3 and number(at[1]) and number(at[2]) and number(at[3]) then
		far = math.abs(at[1]) > 1e6 or math.abs(at[2]) > 1e6 or math.abs(at[3]) > 1e6
	end
	if type(at) ~= "table" or #at ~= 3 or not (number(at[1]) and number(at[2]) and number(at[3])) or far then
		table.insert(out, 'prefab: "at" is [x, y, z], where the prefab\'s origin lands (within a million studs)')
	end
	if spec.turn ~= nil and not (number(spec.turn) and math.abs(spec.turn) <= 3600) then
		table.insert(out, 'prefab: "turn" is a number of degrees (3600 at most, either way)')
	end
	if spec.as ~= nil and not name(spec.as) then
		table.insert(out, 'prefab: "as" is this placement\'s name (letters, digits, _)')
	end
	return out
end

-- what is wrong with a blueprint's "prefabs" ({ [name] = { steps } }), in words; allowed = the kinds a prefab may hold
function Prefab.problems(prefabs: any, allowed: { [string]: boolean }): { string }
	local out: { string } = {}
	if type(prefabs) ~= "table" or #prefabs > 0 then
		return { '"prefabs" is { "<Name>": [steps], ... }' }
	end
	local names: { string } = {}
	for k in prefabs do
		table.insert(names, tostring(k))
	end
	table.sort(names)
	for _, n in names do
		local steps = prefabs[n]
		if not name(n) then
			table.insert(out, `prefabs: "{n}" is no name (letters, digits, _)`)
		elseif type(steps) ~= "table" or #steps == 0 then
			table.insert(out, `prefabs.{n}: a prefab is a list of build steps, and this has none`)
		elseif #steps > Prefab.STEPS then
			table.insert(out, `prefabs.{n}: {#steps} steps (a prefab holds {Prefab.STEPS} at most)`)
		else
			local count: { [string]: number } = {}
			local taken: { [string]: boolean } = {}
			-- (the names its inner placements will have, whatever order they come in: a typed "as" first)
			for _, step in steps do
				local kind, spec = one(step)
				if kind == "prefab" and type(spec) == "table" and name(spec.as) then
					if taken[spec.as] then
						table.insert(out, `prefabs.{n}: two placements in this prefab are called "{spec.as}"`)
					end
					taken[spec.as] = true
				end
			end
			taken = {}
			for i, step in steps do
				local kind, spec = one(step)
				if kind == nil or type(spec) ~= "table" then
					table.insert(
						out,
						`prefabs.{n}[{i}]: a step is one generator: {"{"} "<kind>": {"{"} ... {"}"} {"}"}`
					)
				elseif kind == "prefab" then
					local wrong = Prefab.placement(spec, prefabs)
					for _, p in wrong do
						table.insert(out, `prefabs.{n}[{i}]: {p}`)
					end
					-- (two placements in one prefab may not share a name: their Models would)
					if #wrong == 0 then
						count[spec.name] = (count[spec.name] or 0) + 1
						local called = spec.as or `{spec.name}_{count[spec.name]}`
						if taken[called] then
							table.insert(
								out,
								`prefabs.{n}[{i}]: two placements in this prefab are called "{called}": say another "as" on one of them`
							)
						end
						taken[called] = true
					end
				elseif not allowed[kind] then
					table.insert(
						out,
						`prefabs.{n}[{i}]: a "{kind}" step cannot stand in a prefab: what a prefab holds is moved after it is built, and only steps that make parts and nothing else can be (part, wall, floor, stairs, room, building, mesh, decal, spawn ...)`
					)
				elseif spec.ground == true then
					table.insert(
						out,
						`prefabs.{n}[{i}]: "ground": true cannot be said in a prefab: the land where the step is typed is not the land where the prefab will stand`
					)
				end
			end
		end
	end
	if #out > 0 then
		return out
	end
	-- no prefab holds itself, however far down; none is deeper than DEPTH
	local depthOf: { [string]: number } = {}
	local open: { [string]: boolean } = {}
	local function depth(n: string, trail: string): number
		if depthOf[n] then
			return depthOf[n]
		end
		if open[n] then
			table.insert(out, `prefabs: {trail} -> {n}: a prefab cannot hold itself`)
			return 0
		end
		open[n] = true
		local deepest = 0
		for _, step in prefabs[n] do
			local kind, spec = one(step)
			if kind == "prefab" then
				deepest = math.max(deepest, depth(spec.name, `{trail} -> {n}`))
			end
		end
		open[n] = nil
		depthOf[n] = deepest + 1
		return deepest + 1
	end
	for _, n in names do
		local d = depth(n, "prefabs")
		if #out > 0 then
			return out
		end
		if d > Prefab.DEPTH then
			table.insert(out, `prefabs.{n}: prefabs stand {d} deep in it ({Prefab.DEPTH} at most)`)
		end
	end
	return out
end

export type Move = { dx: number, dy: number, dz: number, deg: number, x: number, z: number }
export type Placed = { step: any, path: string, moves: { Move }, prefix: string, prefab: string }

-- a point turned `deg` degrees about (px, pz), the way the compiler turns a step (World.turnPoint: held to it in the
-- spec)
function Prefab.turn(x: number, z: number, px: number, pz: number, deg: number): (number, number)
	local c, sn = math.cos(math.rad(deg)), math.sin(math.rad(deg))
	if deg % 90 == 0 then
		c, sn = math.round(c), math.round(sn)
	end
	local dx, dz = x - px, z - pz
	return px + c * dx + sn * dz, pz - sn * dx + c * dz
end

-- WHERE A POINT TYPED IN A PREFAB STANDS once its placements have moved it (the innermost first) -> x, y, z, and the
-- turn it has been given in all (degrees)
function Prefab.moved(moves: { Move }, x: number, y: number, z: number): (number, number, number, number)
	local deg = 0
	for _, m in moves do
		x, y, z = x + m.dx, y + m.dy, z + m.dz
		x, z = Prefab.turn(x, z, m.x, m.z, m.deg)
		deg += m.deg
	end
	return x, y, z, deg
end

-- EVERY STEP A BLUEPRINT COMES TO, prefabs opened (each step once for every placement of its prefab, as typed: not
-- moved). What a rule of the build counts - houses typed one by one, rooms, roads - it counts HERE, so that nothing
-- is hidden from it by being put in a prefab. A placement of no prefab, or a prefab that holds itself, is left as
-- the step it is (the compiler says what is wrong with it).
function Prefab.flat(bp: any): { any }
	if type(bp) ~= "table" or type(bp.build) ~= "table" then
		return {}
	end
	if type(bp.prefabs) ~= "table" then
		return bp.build
	end
	local out: { any } = {}
	local function open(steps: { any }, depth: number)
		for _, step in steps do
			local kind, spec = one(step)
			local inner = if kind == "prefab" and type(spec) == "table" then bp.prefabs[spec.name] else nil
			if type(inner) == "table" and depth < Prefab.DEPTH and #out < Prefab.MOST * 2 then
				open(inner, depth + 1)
			else
				table.insert(out, step)
			end
		end
	end
	open(bp.build, 0)
	return out
end

-- ONE PLACEMENT AS THE STEPS IT STANDS FOR (a placement with no problems, of prefabs with none) -> { Placed }, or
-- nil and why. `path` = the placement's own path in the blueprint; `prefix` = its name; `outer` = the moves of the
-- prefabs it stands in (none at the top)
function Prefab.expand(
	spec: any,
	prefabs: any,
	path: string,
	prefix: string,
	outer: { Move }?,
	into: { Placed }?
): ({ Placed }?, string?)
	local out: { Placed } = into or {}
	local turn = spec.turn or 0
	local moves: { Move } =
		{ { dx = spec.at[1], dy = spec.at[2], dz = spec.at[3], deg = turn, x = spec.at[1], z = spec.at[3] } }
	for _, m in outer or {} do
		table.insert(moves, m)
	end
	local seen: { [string]: number } = {}
	for i, step in prefabs[spec.name] do
		local kind, inner = one(step)
		local here = `{path}.{spec.name}[{i}]`
		if kind == "prefab" then
			seen[inner.name] = (seen[inner.name] or 0) + 1
			local child = `{prefix}.{inner.as or `{inner.name}_{seen[inner.name]}`}`
			local _, why = Prefab.expand(inner, prefabs, here, child, moves, out)
			if why then
				return nil, why
			end
		else
			-- (a copy of its own: two placements never share a step's tables)
			table.insert(out, { step = copy(step), path = here, moves = moves, prefix = prefix, prefab = spec.name })
		end
		if #out > Prefab.MOST then
			return nil, `prefabs come to more than {Prefab.MOST} steps in all`
		end
	end
	return out, nil
end

return Prefab
