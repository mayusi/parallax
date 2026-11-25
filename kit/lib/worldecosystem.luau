-- worldecosystem.luau (kit) — A FOREST THAT GREW (the owner's method list: "Ecosystem simulation"). A forest set
-- down by count or by density is trees of chance heights at chance places. A forest that grew has a history: the
-- first trees to reach open ground are the quick ones; under them the slow, shade-bearing ones come up, outlive
-- them and take the ground; old trees fall and leave gaps where the quick ones come back.
--
-- The simulation, year by year (after Deussen et al., "Realistic modeling and rendering of plant ecosystems",
-- 1998: plants as circles that grow, shade each other and seed):
--   1. every plant is a year older; its crown grows to its kind's full width over the kind's `years`;
--   2. a plant older than its kind's `life` dies;
--   3. a plant whose stem stands under the crown of a TALLER plant is in shade (of two as tall, the wider crown
--      shades; of two alike, the one that came up first): each year it dies unless its kind bears shade (`shade`
--      0..1 = its chance to live through a year of it); one that stands in the inner 0.6 of such a crown is
--      crowded out whatever its kind (two trunks do not share one place). A low wide bush shades no tree;
--   4. a full-grown plant seeds: `seeds` a year (the fraction by chance), each thrown up to `throw` studs away;
--      a seed comes up where the land allows, not on another stem, and - under a crown - only by its shade chance.
-- Nothing else is said: who stands where, how old, how thick the wood is and where the clearings are comes out of
-- those four rules and the seed.
-- Pure: no file reads, no game calls.
local Eco = {}

Eco.MOST = 4000 -- plants alive at once (a forest that fills up stops seeding at this many)
Eco.STEM = 3 -- studs between two stems at least
Eco.ROOT = 0.6 -- the share of a crown's radius, from its stem, in which no lesser plant lives
Eco.FINE = 8 -- studs: the cell of the grid every plant is kept in; a crown wider than this is kept in a second one
Eco.SEEDLING = 20 -- studs a seedling may be tall at most (taller ones' trunks would touch at STEM apart)
Eco.DEFAULTS = { years = 80, first = 6 }

local function lcg(seed: number): () -> number
	local state = (seed or 1) % 2147483647
	if state <= 0 then
		state += 2147483646
	end
	state = (state * 48271) % 2147483647
	state = (state * 48271) % 2147483647
	return function()
		state = (state * 48271) % 2147483647
		return state / 2147483647
	end
end

local function number(v: any): boolean
	return type(v) == "number" and v == v and v ~= math.huge and v ~= -math.huge
end

local KEYS = { years = true, first = true, species = true }
local SPECIES = {
	name = true,
	style = true,
	height = true,
	crown = true,
	years = true,
	life = true,
	shade = true,
	seeds = true,
	throw = true,
	first = true,
	meshes = true,
}

-- the forest's tree styles a kind may name (kit/lib/world.luau buildTree)
Eco.STYLES = { "oak", "dead", "pine", "palm", "jungle", "fern", "bush", "golden" }

-- what is wrong with an ecosystem (nothing = it can be run)
--   { years: 80, first: 6 (seedlings of each kind at year 0), species: [ { name, style?: a forest style (or
--     meshes?: [world mesh names], one of them each tree),
--     height: [seedling, grown] studs, crown: full width in studs, years: to full size, life: years it lives,
--     shade: 0..1, seeds: a year once grown, throw: studs a seed travels at most, first?: its own seedlings } ] }
function Eco.problems(spec: any): { string }
	local out: { string } = {}
	if type(spec) ~= "table" then
		return { "an ecosystem is { years, species: [ { name, height, crown, years, life, shade, seeds, throw } ] }" }
	end
	for k in spec do
		if not KEYS[k] then
			table.insert(out, `ecosystem.{tostring(k)} is not a word an ecosystem knows (years, first, species)`)
		end
	end
	local function whole(v: any, lo: number, hi: number): boolean
		return number(v) and v % 1 == 0 and v >= lo and v <= hi
	end
	if spec.years ~= nil and not whole(spec.years, 0, 400) then
		table.insert(out, `ecosystem.years is a whole number 0 to 400 (got {tostring(spec.years)})`)
	end
	if spec.first ~= nil and not whole(spec.first, 0, 200) then
		table.insert(out, `ecosystem.first is a whole number 0 to 200 (got {tostring(spec.first)})`)
	end
	local list = spec.species
	if type(list) ~= "table" or #list < 1 or #list > 6 then
		table.insert(out, "ecosystem.species is a list of one to six kinds of plant")
		return out
	end
	local names: { [string]: boolean } = {}
	for i, s in list do
		local at = `ecosystem.species[{i}]`
		if type(s) ~= "table" then
			table.insert(out, `{at} is \{ name, height, crown, years, life, shade, seeds, throw \}`)
			continue
		end
		for k in s do
			if not SPECIES[k] then
				table.insert(
					out,
					`{at}.{tostring(k)} is not a word a kind knows (name, style, meshes, height, crown, years, life, shade, seeds, throw, first)`
				)
			end
		end
		if type(s.name) ~= "string" or s.name == "" then
			table.insert(out, `{at}.name is the kind's name`)
		elseif names[s.name] then
			table.insert(out, `{at}.name "{s.name}" is used twice`)
		else
			names[s.name] = true
		end
		if s.style ~= nil and (type(s.style) ~= "string" or not table.find(Eco.STYLES, s.style)) then
			table.insert(out, `{at}.style is one of the forest's tree styles: {table.concat(Eco.STYLES, ", ")}`)
		end
		if s.meshes ~= nil then
			local ok = type(s.meshes) == "table" and #s.meshes >= 1
			for _, m in if ok then s.meshes else {} do
				ok = ok and type(m) == "string" and m ~= ""
			end
			if not ok then
				table.insert(out, `{at}.meshes is a list of world mesh names (one of them each tree)`)
			elseif s.style ~= nil then
				table.insert(out, `{at} says "style" and "meshes": a kind is built one way`)
			end
		end
		local h = s.height
		if
			type(h) ~= "table"
			or #h ~= 2
			or not (number(h[1]) and number(h[2]))
			or h[1] < 2
			or h[1] > Eco.SEEDLING
			or h[2] < h[1]
			or h[2] > 200
		then
			table.insert(
				out,
				`{at}.height is [seedling, grown] in studs: the seedling 2 to {Eco.SEEDLING}, the grown no less, 200 at most`
			)
		end
		if not number(s.crown) or s.crown < 4 or s.crown > 120 then
			table.insert(out, `{at}.crown is the grown crown's width, 4 to 120 studs (got {tostring(s.crown)})`)
		elseif type(h) == "table" and number(h[2]) and s.crown < h[2] * 0.5 then
			-- (grown trees stand no closer than 0.6 of a crown's radius: with a crown under half the height that is
			-- under a seventh of the height, and two trunks - a tenth of the height thick as built - would nearly
			-- touch. Built crowns are wider than this asks, about as wide as the tree is tall: they interlock)
			table.insert(
				out,
				`{at}.crown ({s.crown}) is under half its grown height ({h[2]}): its grown trees would stand nearly trunk to trunk`
			)
		end
		if not whole(s.years, 1, 200) then
			table.insert(out, `{at}.years is how long it takes to full size, a whole number 1 to 200`)
		end
		if not whole(s.life, 1, 1000) or (whole(s.years, 1, 200) and s.life < s.years) then
			table.insert(
				out,
				`{at}.life is how long it lives, a whole number of years, no less than its years to full size`
			)
		end
		if not number(s.shade) or s.shade < 0 or s.shade > 1 then
			table.insert(out, `{at}.shade is 0 (dies in shade) to 1 (lives in it) (got {tostring(s.shade)})`)
		end
		if not number(s.seeds) or s.seeds < 0 or s.seeds > 20 then
			table.insert(out, `{at}.seeds is how many a grown plant sets a year, 0 to 20 (got {tostring(s.seeds)})`)
		end
		if not number(s.throw) or s.throw < Eco.STEM or s.throw > 400 then
			table.insert(out, `{at}.throw is how far a seed travels at most, {Eco.STEM} to 400 studs`)
		end
		if s.first ~= nil and not whole(s.first, 0, 200) then
			table.insert(out, `{at}.first is a whole number 0 to 200`)
		end
	end
	return out
end

-- a plant's crown radius and height at an age
function Eco.size(kind: any, age: number): (number, number)
	local grown = math.min(1, age / kind.years)
	return kind.crown / 2 * grown, kind.height[1] + (kind.height[2] - kind.height[1]) * grown
end

-- DOES PLANT a KEEP THE LIGHT FROM PLANT b (were b's stem under a's crown): the taller does; of two as tall the
-- wider; of two alike the one that came up first (`order`)
function Eco.shades(a: any, b: any): boolean
	if a.height ~= b.height then
		return a.height > b.height
	elseif a.radius ~= b.radius then
		return a.radius > b.radius
	end
	return a.order < b.order
end

-- THE RUN (a spec with no problems). area = { w, d } studs round (0, 0); site(x, z) -> false where no plant may
-- stand (water, a road, off the land); nil = anywhere.
-- -> { plants = { { x, z, kind (index), age, radius, height, born (the year), from (studs from its parent's stem,
--      nil for the first) } } (the living, oldest first), years, census = { [year] = { [kind index] = living } }
--      (year 0 and every tenth year and the last), dead = { old, shade, crowd } (how many died of each),
--      full = true when the forest reached MOST, first = { asked, set }: the first seedlings asked for and
--      those that found a place }
function Eco.run(spec: any, area: { number }, seed: number?, site: ((number, number) -> boolean)?): any
	local rnd = lcg(seed or 1)
	local kinds = spec.species
	local years = spec.years or Eco.DEFAULTS.years
	local hw, hd = area[1] / 2, area[2] / 2
	local widest = Eco.FINE
	for _, k in kinds do
		widest = math.max(widest, k.crown / 2)
	end
	-- the living, in two grids: every plant in one of FINE-stud cells (a stem that is too near, a crown no wider
	-- than a cell, are in the nine cells round a place); a plant whose crown is wider than a cell also in one of
	-- cells as wide as the widest crown's radius (there are few of those: a forest of small plants under one giant
	-- does not look through all of itself at every step)
	local fine: { [number]: { any } } = {}
	local wide: { [number]: { any } } = {}
	local living: { any } = {}
	local function put(grid: { [number]: { any } }, cell: number, q: any)
		local k = math.floor((q.z + hd) / cell) * 4096 + math.floor((q.x + hw) / cell)
		local bucket = grid[k]
		if not bucket then
			bucket = {}
			grid[k] = bucket
		end
		table.insert(bucket, q)
	end
	local function near(
		grid: { [number]: { any } },
		cell: number,
		x: number,
		z: number,
		each: (any) -> boolean?
	): boolean
		local ci, cj = math.floor((x + hw) / cell), math.floor((z + hd) / cell)
		for j = cj - 1, cj + 1 do
			for i = ci - 1, ci + 1 do
				local bucket = grid[j * 4096 + i]
				if bucket then
					for _, q in bucket do
						if not q.gone and each(q) then
							return true
						end
					end
				end
			end
		end
		return false
	end
	local function free(x: number, z: number): boolean
		if x < -hw or x > hw or z < -hd or z > hd or (site and not site(x, z)) then
			return false
		end
		return not near(fine, Eco.FINE, x, z, function(q)
			return (q.x - x) ^ 2 + (q.z - z) ^ 2 < Eco.STEM ^ 2
		end)
	end
	-- is the plant `me` (its place, height, radius, order) under the crown of one that keeps the light from it
	-- -> 0 no | 1 in its shade | 2 in its inner part (crowded out)
	local function shaded(me: any): number
		local under = 0
		local function look(q: any): boolean?
			if q ~= me and q.radius > 0 and Eco.shades(q, me) then
				local d2 = (q.x - me.x) ^ 2 + (q.z - me.z) ^ 2
				if d2 < (q.radius * Eco.ROOT) ^ 2 then
					under = 2
					return true
				elseif d2 < q.radius ^ 2 then
					under = 1
				end
			end
			return nil
		end
		-- (a crown no wider than a fine cell is in the fine grid's nine cells; a wider one in the wide grid's - and
		-- only there is it asked, so it is not counted twice)
		if not near(fine, Eco.FINE, me.x, me.z, function(q)
			return if q.wide then nil else look(q)
		end) then
			near(wide, widest, me.x, me.z, look)
		end
		return under
	end
	local order = 0
	local function add(x: number, z: number, k: number, born: number, from: number?)
		local radius, height = Eco.size(kinds[k], 0)
		order += 1
		local p = {
			x = x,
			z = z,
			kind = k,
			age = 0,
			radius = radius,
			height = height,
			born = born,
			from = from,
			order = order,
		}
		table.insert(living, p)
		put(fine, Eco.FINE, p)
	end
	local census: { [number]: { number } } = {}
	local function count(year: number)
		local n = table.create(#kinds, 0)
		for _, p in living do
			n[p.kind] += 1
		end
		census[year] = n
	end
	-- year 0: the first seedlings of each kind, at chance places
	local first = { asked = 0, set = 0 }
	for k, kind in kinds do
		local want = kind.first or spec.first or Eco.DEFAULTS.first
		local tries = 0
		local set = 0
		while set < want and tries < want * 40 do
			tries += 1
			local x, z = (rnd() - 0.5) * area[1], (rnd() - 0.5) * area[2]
			if free(x, z) then
				add(x, z, k, 0, nil)
				set += 1
			end
		end
		first.asked += want
		first.set += set
	end
	count(0)
	local dead = { old = 0, shade = 0, crowd = 0 }
	local full = false
	for year = 1, years do
		-- 1. a year older, a year wider (a crown that has outgrown a fine cell is kept in the wide grid too)
		for _, q in living do
			q.age += 1
			q.radius, q.height = Eco.size(kinds[q.kind], q.age)
			if not q.wide and q.radius > Eco.FINE then
				q.wide = true
				put(wide, widest, q)
			end
		end
		-- 2. and 3. the old die; the shaded die unless their kind bears it. Who is shaded is read off the forest
		-- as it stands at the year's start, for every plant alike (one that dies this year still shaded its
		-- neighbours this year); the chance is drawn for every shaded plant in the order they stand in the list:
		-- the same seed, the same forest
		local going: { any } = {}
		for _, q in living do
			if q.age > kinds[q.kind].life then
				table.insert(going, q)
				dead.old += 1
			else
				local under = shaded(q)
				if under == 2 then
					table.insert(going, q)
					dead.crowd += 1
				elseif under == 1 and rnd() >= kinds[q.kind].shade then
					table.insert(going, q)
					dead.shade += 1
				end
			end
		end
		for _, q in going do
			q.gone = true
		end
		local kept: { any } = {}
		for _, q in living do
			if not q.gone then
				table.insert(kept, q)
			end
		end
		living = kept
		for _, grid in { fine, wide } do
			for k, bucket in grid do
				local left: { any } = {}
				for _, q in bucket do
					if not q.gone then
						table.insert(left, q)
					end
				end
				grid[k] = if #left > 0 then left else nil
			end
		end
		-- 4. the grown seed (those that stood at the year's start: a seedling does not seed)
		local parents = #living
		for i = 1, parents do
			local p = living[i]
			local kind = kinds[p.kind]
			if p.age >= kind.years and kind.seeds > 0 then
				local n = math.floor(kind.seeds)
				if rnd() < kind.seeds - n then
					n += 1
				end
				for _ = 1, n do
					local turn, far = rnd() * 2 * math.pi, kind.throw * math.sqrt(rnd())
					local chance = rnd()
					if #living >= Eco.MOST then
						full = true
						continue
					end
					local x, z = p.x + math.cos(turn) * far, p.z + math.sin(turn) * far
					local under = if free(x, z)
						then shaded({ x = x, z = z, height = kind.height[1], radius = 0, order = math.huge })
						else 2
					if under == 0 or (under == 1 and chance < kind.shade) then
						add(x, z, p.kind, year, far)
					end
				end
			end
		end
		if year % 10 == 0 or year == years then
			count(year)
		end
	end
	table.sort(living, function(a, b)
		if a.age ~= b.age then
			return a.age > b.age
		elseif a.x ~= b.x then
			return a.x < b.x
		end
		return a.z < b.z
	end)
	local plants: { any } = {}
	for _, p in living do
		table.insert(plants, {
			x = p.x,
			z = p.z,
			kind = p.kind,
			age = p.age,
			radius = p.radius,
			height = p.height,
			born = p.born,
			from = p.from,
		})
	end
	return { plants = plants, years = years, census = census, dead = dead, full = full, first = first }
end

return Eco
