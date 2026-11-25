-- worldwfc.luau (kit) — A PLACE LAID OUT OF TILES THAT FIT (the owner's method list: "Wave function collapse",
-- "Tile-based world building"). A tile set is a handful of square pieces - a stretch of wall, a corner, a gate, an
-- open court - each with a word on each of its four sides ("wall", "open", "road" ...). Two tiles may lie side by
-- side only where the words on the sides that touch are the same. The collapse fills a grid with them:
--   every cell starts as "any tile, any turn"; the cell with the fewest left is settled on one of them (by weight,
--   by the seed); what its neighbours can still be is cut down to what fits it, and theirs in turn; and so on until
--   every cell is settled. A cell left with nothing is a dead end: the whole grid is begun again (a set number of
--   times) from further on in the seed's numbers.
-- So no two neighbours ever clash - by construction, and checked on the result (Wfc.clashes).
-- A tile may be laid in its four quarter turns (unless it says "turns": false). Turn t is t quarter turns CLOCKWISE
-- seen from above: what faced north faces east.
-- Sides are numbered 1 north (-z), 2 east (+x), 3 south (+z), 4 west (-x).
-- Pure: no file reads, no game calls.
local Wfc = {}

Wfc.TRIES = 40 -- times a grid is begun again before it is given up
Wfc.CELLS = 2500 -- cells a grid may have
Wfc.TILES = 40 -- tiles a set may have
Wfc.PARTS = 40 -- parts a tile may have

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

local function whole(v: any, lo: number, hi: number): boolean
	return number(v) and v % 1 == 0 and v >= lo and v <= hi
end

local KEYS = {
	name = true,
	center = true,
	cell = true,
	grid = true,
	seed = true,
	set = true,
	fixed = true,
	stream = true,
	landmark = true,
}
local SET = { tiles = true, border = true }
local TILE = { name = true, edges = true, weight = true, turns = true, parts = true }
local PART = { name = true, size = true, pos = true, mat = true }

-- what is wrong with a tiles step (nothing = it can be laid out)
--   { name?, center: [x, y, z], cell: studs a tile is wide, grid: [across, deep], seed?,
--     set: { tiles: [ { name, edges: [north, east, south, west], weight?: 1, turns?: true,
--                       parts: [ { size: [x, y, z], pos: [x, y, z] from the tile's middle on the ground, mat } ] } ],
--            border?: the word every outer side of the grid shows },
--     fixed?: [ { at: [i, j], tile: name, turn?: 0..3 } ] }
function Wfc.problems(spec: any): { string }
	local out: { string } = {}
	if type(spec) ~= "table" then
		return { "tiles is { center, cell, grid: [across, deep], set: { tiles: [...] } }" }
	end
	for k in spec do
		if not KEYS[k] then
			table.insert(out, `tiles.{tostring(k)} is not a word it knows (name, center, cell, grid, seed, set, fixed)`)
		end
	end
	if spec.name ~= nil and (type(spec.name) ~= "string" or spec.name == "") then
		table.insert(out, "tiles.name is its name")
	end
	local c = spec.center
	local function place(v: any): boolean
		return number(v) and math.abs(v) <= 1e6
	end
	if type(c) ~= "table" or #c ~= 3 or not (place(c[1]) and place(c[2]) and place(c[3])) then
		table.insert(out, "tiles.center is [x, y, z] (the ground the tiles stand on is at y)")
	end
	if not number(spec.cell) or spec.cell < 4 or spec.cell > 256 then
		table.insert(out, `tiles.cell is how wide a tile is, 4 to 256 studs (got {tostring(spec.cell)})`)
	end
	local g = spec.grid
	local gridOk = type(g) == "table" and #g == 2 and whole(g[1], 1, 200) and whole(g[2], 1, 200)
	if not gridOk or g[1] * g[2] > Wfc.CELLS then
		table.insert(out, `tiles.grid is [across, deep] in tiles, whole numbers, {Wfc.CELLS} cells at most`)
		gridOk = false
	end
	if spec.seed ~= nil and not whole(spec.seed, 0, 65535) then
		table.insert(out, `tiles.seed is a whole number 0 to 65535 (got {tostring(spec.seed)})`)
	end
	local set = spec.set
	if type(set) ~= "table" or type(set.tiles) ~= "table" or #set.tiles < 1 or #set.tiles > Wfc.TILES then
		table.insert(out, `tiles.set is \{ tiles: [ one to {Wfc.TILES} tiles ], border? \}`)
		return out
	end
	for k in set do
		if not SET[k] then
			table.insert(out, `tiles.set.{tostring(k)} is not a word a set knows (tiles, border)`)
		end
	end
	local names: { [string]: boolean } = {}
	local words: { [string]: boolean } = {}
	for i, t in set.tiles do
		local at = `tiles.set.tiles[{i}]`
		if type(t) ~= "table" then
			table.insert(out, `{at} is \{ name, edges: [north, east, south, west], parts: [...] \}`)
			continue
		end
		for k in t do
			if not TILE[k] then
				table.insert(out, `{at}.{tostring(k)} is not a word a tile knows (name, edges, weight, turns, parts)`)
			end
		end
		if type(t.name) ~= "string" or t.name == "" then
			table.insert(out, `{at}.name is the tile's name`)
		elseif names[t.name] then
			table.insert(out, `{at}.name "{t.name}" is used twice`)
		else
			names[t.name] = true
		end
		local e = t.edges
		local edgesOk = type(e) == "table" and #e == 4
		for d = 1, 4 do
			edgesOk = edgesOk and type(e[d]) == "string" and e[d] ~= ""
		end
		if not edgesOk then
			table.insert(out, `{at}.edges is the word on each side: [north, east, south, west]`)
		else
			for d = 1, 4 do
				words[e[d]] = true
			end
		end
		if t.weight ~= nil and (not number(t.weight) or t.weight <= 0 or t.weight > 1000) then
			table.insert(out, `{at}.weight is how often it is taken beside the others, over 0 to 1000`)
		end
		if t.turns ~= nil and type(t.turns) ~= "boolean" then
			table.insert(out, `{at}.turns is true (laid in any quarter turn) or false (only as written)`)
		end
		local listed = 0
		for _ in if type(t.parts) == "table" then t.parts else {} do
			listed += 1
		end
		if type(t.parts) ~= "table" or #t.parts > Wfc.PARTS or listed ~= #t.parts then
			table.insert(out, `{at}.parts is a list of parts, {Wfc.PARTS} at most (an empty list is an empty tile)`)
		else
			for k, p in t.parts do
				local where = `{at}.parts[{k}]`
				if type(p) ~= "table" then
					table.insert(out, `{where} is \{ size: [x, y, z], pos: [x, y, z], mat \}`)
					continue
				end
				if p.name ~= nil and (type(p.name) ~= "string" or p.name == "") then
					table.insert(out, `{where}.name is its name`)
				end
				for word in p do
					if not PART[word] then
						table.insert(
							out,
							`{where}.{tostring(word)} is not a word a tile's part knows (name, size, pos, mat)`
						)
					end
				end
				local s, q = p.size, p.pos
				if
					type(s) ~= "table"
					or #s ~= 3
					or not (number(s[1]) and number(s[2]) and number(s[3]))
					or math.min(s[1], s[2], s[3]) < 0.05
				then
					table.insert(out, `{where}.size is [x, y, z] in studs, 0.05 or more each`)
				elseif type(q) ~= "table" or #q ~= 3 or not (number(q[1]) and number(q[2]) and number(q[3])) then
					table.insert(out, `{where}.pos is [x, y, z] from the tile's middle on the ground`)
				elseif
					number(spec.cell)
					and (
						math.abs(q[1]) + s[1] / 2 > spec.cell / 2 + 1e-9
						or math.abs(q[3]) + s[3] / 2 > spec.cell / 2 + 1e-9
					)
				then
					-- (a part that reaches over its tile's side would stand in the neighbour, whatever that is)
					table.insert(out, `{where} reaches over the side of its tile ({spec.cell} studs wide)`)
				elseif q[2] + s[2] / 2 < 0 then
					table.insert(
						out,
						`{where} lies wholly under the ground (its pos is from the tile's middle ON the ground)`
					)
				end
				if type(p.mat) ~= "string" or p.mat == "" then
					table.insert(out, `{where}.mat is a palette entry's name`)
				end
			end
		end
	end
	if set.border ~= nil and (type(set.border) ~= "string" or not words[set.border]) then
		table.insert(out, `tiles.set.border is a word some tile has on a side (got {tostring(set.border)})`)
	end
	if spec.fixed ~= nil then
		if type(spec.fixed) ~= "table" then
			table.insert(out, "tiles.fixed is a list of { at: [i, j], tile, turn? }")
		else
			local taken: { [number]: boolean } = {}
			for k, f in spec.fixed do
				local at = `tiles.fixed[{k}]`
				if type(f) ~= "table" or type(f.at) ~= "table" or #f.at ~= 2 or type(f.tile) ~= "string" then
					table.insert(out, `{at} is \{ at: [i, j], tile: a tile's name, turn?: 0 to 3 \}`)
					continue
				end
				if gridOk and not (whole(f.at[1], 1, g[1]) and whole(f.at[2], 1, g[2])) then
					table.insert(out, `{at}.at is a cell of the grid: [1..{g[1]}, 1..{g[2]}]`)
				elseif gridOk then
					local key = f.at[2] * 1000 + f.at[1]
					if taken[key] then
						table.insert(out, `{at}.at: that cell is fixed twice`)
					end
					taken[key] = true
				end
				if not names[f.tile] then
					table.insert(out, `{at}.tile "{f.tile}" is no tile of the set`)
				end
				if f.turn ~= nil and not whole(f.turn, 0, 3) then
					table.insert(out, `{at}.turn is 0 to 3 quarter turns`)
				elseif f.turn ~= nil and f.turn ~= 0 then
					for _, t in set.tiles do
						if type(t) == "table" and t.name == f.tile and t.turns == false then
							table.insert(out, `{at}.turn: the tile "{f.tile}" is laid only as written ("turns": false)`)
						end
					end
				end
				for word in f do
					if word ~= "at" and word ~= "tile" and word ~= "turn" then
						table.insert(out, `{at}.{tostring(word)} is not a word it knows (at, tile, turn)`)
					end
				end
			end
		end
	end
	return out
end

-- THE WAYS A SET'S TILES CAN LIE: each tile in each of its turns - { tile (index), turn (0..3), edges = the words
-- on its north, east, south, west as it lies, weight }. Every turn is a way of its own, also where the four words
-- read the same turned (the tile's PARTS still turn: a court with a bench on one side); a tile's weight is shared
-- out over its ways, so that a tile is taken as often as its weight says however many turns it has. Turn t: what
-- faced north faces t sides on, clockwise.
function Wfc.ways(set: any): { any }
	local out: { any } = {}
	for i, t in set.tiles do
		local turns = if t.turns == false then 1 else 4
		for turn = 0, turns - 1 do
			local edges = table.create(4)
			for d = 1, 4 do
				edges[d] = t.edges[(d - 1 - turn) % 4 + 1]
			end
			table.insert(out, { tile = i, turn = turn, edges = edges, weight = (t.weight or 1) / turns })
		end
	end
	return out
end

local STEP = { { 0, -1 }, { 1, 0 }, { 0, 1 }, { -1, 0 } } -- (north, east, south, west: i, j)

-- THE LAYOUT (a spec with no problems) -> grid[i][j] = { tile (index), turn }, tries (how many times it was
-- begun) - or nil, why
function Wfc.solve(spec: any): (any?, any)
	local set = spec.set
	local ways = Wfc.ways(set)
	local nx, nz = spec.grid[1], spec.grid[2]
	local rnd = lcg(spec.seed or 1)
	local n = #ways
	-- fits[d][a] = the ways that may lie on side d of way a
	local fits: { { { number } } } = {}
	for d = 1, 4 do
		fits[d] = {}
		local back = (d + 1) % 4 + 1
		for a = 1, n do
			local list = {}
			for b = 1, n do
				if ways[a].edges[d] == ways[b].edges[back] then
					table.insert(list, b)
				end
			end
			fits[d][a] = list
		end
	end
	local fixedAt: { [number]: any } = {}
	for _, f in spec.fixed or {} do
		fixedAt[f.at[2] * 1000 + f.at[1]] = f
	end
	local function begin(): ({ { { boolean } } }, { { number } }, string?)
		local can: { { { boolean } } } = table.create(nx)
		local left: { { number } } = table.create(nx)
		for i = 1, nx do
			can[i] = table.create(nz)
			left[i] = table.create(nz, 0)
			for j = 1, nz do
				local cell = table.create(n, false)
				local count = 0
				local f = fixedAt[j * 1000 + i]
				for a = 1, n do
					local w = ways[a]
					local ok = true
					if set.border then
						ok = (j > 1 or w.edges[1] == set.border)
							and (i < nx or w.edges[2] == set.border)
							and (j < nz or w.edges[3] == set.border)
							and (i > 1 or w.edges[4] == set.border)
					end
					if ok and f then
						ok = set.tiles[w.tile].name == f.tile and (f.turn == nil or f.turn == w.turn)
					end
					cell[a] = ok
					count += if ok then 1 else 0
				end
				if count == 0 then
					return can,
						left,
						if f
							then `the tile fixed at [{i}, {j}] ("{f.tile}") cannot lie there{if set.border
								then " (the border's word is not on its outer side)"
								else ""}`
							else `no tile can lie at [{i}, {j}]: none shows the border's word "{set.border}" on the grid's outer side there`
				end
				can[i][j] = cell
				left[i][j] = count
			end
		end
		return can, left, nil
	end
	-- cut a cell's neighbours down to what fits what it can still be; -> false when a cell is left with nothing
	local function spread(can: { { { boolean } } }, left: { { number } }, queue: { { number } }): boolean
		local head = 1
		while head <= #queue do
			local i, j = queue[head][1], queue[head][2]
			head += 1
			for d = 1, 4 do
				local a, b = i + STEP[d][1], j + STEP[d][2]
				if a >= 1 and a <= nx and b >= 1 and b <= nz then
					local allowed = table.create(n, false)
					for w = 1, n do
						if can[i][j][w] then
							for _, v in fits[d][w] do
								allowed[v] = true
							end
						end
					end
					local changed = false
					for w = 1, n do
						if can[a][b][w] and not allowed[w] then
							can[a][b][w] = false
							left[a][b] -= 1
							changed = true
						end
					end
					if left[a][b] == 0 then
						return false
					end
					if changed then
						table.insert(queue, { a, b })
					end
				end
			end
		end
		return true
	end
	local why = "the tiles do not fit together on this grid"
	for try = 1, Wfc.TRIES do
		local can, left, wrong = begin()
		if wrong then
			return nil, wrong
		end
		-- (what the border and the fixed tiles already rule out, everywhere)
		local all: { { number } } = {}
		for i = 1, nx do
			for j = 1, nz do
				table.insert(all, { i, j })
			end
		end
		local ok = spread(can, left, all)
		if not ok then
			-- (nothing was chosen yet: beginning again would come to the same)
			return nil,
				"the tiles do not fit together on this grid: with its border and its fixed tiles some cell has no tile left before any is chosen"
		end
		local settled: { { boolean } } = table.create(nx)
		for i = 1, nx do
			settled[i] = table.create(nz, false)
		end
		local open = nx * nz
		while ok and open > 0 do
			-- the cell with the fewest ways left (of equals, one by the seed)
			local least, ties = math.huge, 0
			local pi, pj = 0, 0
			for i = 1, nx do
				for j = 1, nz do
					if not settled[i][j] then
						if left[i][j] < least then
							least, ties = left[i][j], 1
							pi, pj = i, j
						elseif left[i][j] == least then
							ties += 1
							if rnd() * ties < 1 then
								pi, pj = i, j
							end
						end
					end
				end
			end
			-- one of its ways, by weight
			local total = 0
			for w = 1, n do
				if can[pi][pj][w] then
					total += ways[w].weight
				end
			end
			local pick = rnd() * total
			local chosen = 0
			for w = 1, n do
				if can[pi][pj][w] then
					chosen = w
					pick -= ways[w].weight
					if pick < 0 then
						break
					end
				end
			end
			for w = 1, n do
				can[pi][pj][w] = w == chosen
			end
			left[pi][pj] = 1
			settled[pi][pj] = true
			open -= 1
			ok = spread(can, left, { { pi, pj } })
		end
		if ok then
			local grid: { { any } } = table.create(nx)
			for i = 1, nx do
				grid[i] = table.create(nz)
				for j = 1, nz do
					for w = 1, n do
						if can[i][j][w] then
							grid[i][j] = { tile = ways[w].tile, turn = ways[w].turn }
						end
					end
				end
			end
			return grid, try
		end
	end
	return nil, `{why} (begun {Wfc.TRIES} times)`
end

-- the word a laid tile shows on a side (1 north .. 4 west)
function Wfc.edge(set: any, laid: any, side: number): string
	return set.tiles[laid.tile].edges[(side - 1 - laid.turn) % 4 + 1]
end

-- HOW MANY PAIRS OF NEIGHBOURS CLASH in a layout, and how many outer sides do not show the border's word (0 and 0
-- in a layout that can be built) - counted on the layout as it is, not on how it was made
function Wfc.clashes(spec: any, grid: any): (number, number)
	local set = spec.set
	local nx, nz = spec.grid[1], spec.grid[2]
	local clash, edge = 0, 0
	for i = 1, nx do
		for j = 1, nz do
			if i < nx and Wfc.edge(set, grid[i][j], 2) ~= Wfc.edge(set, grid[i + 1][j], 4) then
				clash += 1
			end
			if j < nz and Wfc.edge(set, grid[i][j], 3) ~= Wfc.edge(set, grid[i][j + 1], 1) then
				clash += 1
			end
			if set.border then
				for d = 1, 4 do
					local a, b = i + STEP[d][1], j + STEP[d][2]
					if (a < 1 or a > nx or b < 1 or b > nz) and Wfc.edge(set, grid[i][j], d) ~= set.border then
						edge += 1
					end
				end
			end
		end
	end
	return clash, edge
end

-- a point of a tile (x, z from its middle) as the tile lies in a turn: t quarter turns clockwise seen from above
function Wfc.turned(x: number, z: number, turn: number): (number, number)
	for _ = 1, turn % 4 do
		x, z = 0 - z, x -- (0 - z: a turned 0 is 0, never -0)
	end
	return x, z
end

return Wfc
