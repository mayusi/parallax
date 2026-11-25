-- worldwfc.spec.luau (kit) — A PLACE LAID OUT OF TILES THAT FIT (kit/lib/worldwfc.luau; the owner's method list: "Wave
-- function collapse", "Tile-based world building"). The layout is held to the one thing the method promises - no two
-- neighbours clash, the border shows its word, the fixed tiles lie where they were put - by a count of this file's
-- own; and the parts the compiler makes of it to the tiles' own parts, turned with their tile: where two tiles meet
-- on a "wall" side, their walls meet.
-- Not claimed here: that a place laid out this way is a good place, or can be walked from end to end (the method
-- does not promise it). That is a built world, checked and looked at.
local frk = require("../frk")
local test, check = frk.test, frk.check

local Wfc = require("../../lib/worldwfc")
local World = require("../../lib/world")

local PALETTE = {
	stone = { material = "Slate", color = { 90, 90, 90 } },
	flag = { material = "Cobblestone", color = { 110, 108, 100 } },
}

-- a wall's stub from a tile's middle to one side (16-stud tiles): { which side as written, part }
local function stub(side: number): any
	local dir = ({ { 0, -1 }, { 1, 0 }, { 0, 1 }, { -1, 0 } })[side]
	return {
		name = "Wall",
		size = if dir[1] ~= 0 then { 8, 10, 2 } else { 2, 10, 8 },
		pos = { dir[1] * 4, 5, dir[2] * 4 },
		mat = "stone",
	}
end
local FLOOR = { name = "Floor", size = { 16, 1, 16 }, pos = { 0, -0.5, 0 }, mat = "flag" }

local function tile(name: string, edges: { string }, weight: number?): any
	local parts = { FLOOR }
	for side = 1, 4 do
		if edges[side] == "wall" then
			table.insert(parts, stub(side))
		end
	end
	return { name = name, edges = edges, weight = weight, parts = parts }
end

local function ruin(): any
	return {
		border = "open",
		tiles = {
			tile("court", { "open", "open", "open", "open" }, 3),
			tile("wall", { "open", "wall", "open", "wall" }, 2),
			tile("corner", { "open", "wall", "wall", "open" }, 1),
			tile("end", { "open", "wall", "open", "open" }, 0.5),
			tile("tee", { "open", "wall", "wall", "wall" }, 0.5),
		},
	}
end

local function spec(more: any?): any
	local s: any = { name = "Ruin", center = { 0, 0, 0 }, cell = 16, grid = { 12, 9 }, seed = 5, set = ruin() }
	for k, v in more or {} do
		s[k] = v
	end
	return s
end

-- the word a laid tile shows on a side, by this file's own turning of the tile's list (a quarter turn clockwise:
-- the last word comes to the front)
local function shows(set: any, laid: any, side: number): string
	local e = table.clone(set.tiles[laid.tile].edges)
	for _ = 1, laid.turn do
		table.insert(e, 1, table.remove(e) :: string)
	end
	return e[side]
end

local function clashes(s: any, grid: any): (number, number)
	local clash, edge = 0, 0
	for i = 1, s.grid[1] do
		for j = 1, s.grid[2] do
			if i < s.grid[1] and shows(s.set, grid[i][j], 2) ~= shows(s.set, grid[i + 1][j], 4) then
				clash += 1
			end
			if j < s.grid[2] and shows(s.set, grid[i][j], 3) ~= shows(s.set, grid[i][j + 1], 1) then
				clash += 1
			end
			if s.set.border then
				edge += if j == 1 and shows(s.set, grid[i][j], 1) ~= s.set.border then 1 else 0
				edge += if i == s.grid[1] and shows(s.set, grid[i][j], 2) ~= s.set.border then 1 else 0
				edge += if j == s.grid[2] and shows(s.set, grid[i][j], 3) ~= s.set.border then 1 else 0
				edge += if i == 1 and shows(s.set, grid[i][j], 4) ~= s.set.border then 1 else 0
			end
		end
	end
	return clash, edge
end

local function compile(s: any): (any, { any }, { string }, any)
	local model, parts, issues, extras =
		World.compile({ name = "T", scale = "r6", palette = PALETTE, build = { { tiles = s } } })
	local errors = {}
	for _, i in issues do
		if i.severity == "error" then
			table.insert(errors, i.message)
		end
	end
	return model, parts, errors, extras
end

return function()
	test.suite("A place laid out of tiles that fit", function()
		test.case("what is wrong with a tiles step is said", function()
			local function wrong(more: any, text: string)
				local problems = Wfc.problems(spec(more))
				check.truthy(#problems >= 1)
				check.truthy(string.find(table.concat(problems, " | "), text, 1, true), table.concat(problems, " | "))
			end
			local function set(change: (any) -> ()): any
				local s = ruin()
				change(s)
				return { set = s }
			end
			check.equal(#Wfc.problems(spec()), 0)
			check.equal(
				#Wfc.problems(
					spec({ fixed = { { at = { 3, 3 }, tile = "court" }, { at = { 4, 3 }, tile = "wall", turn = 1 } } })
				),
				0
			)
			check.equal(#Wfc.problems(spec({
				grid = { 50, 50 },
				seed = 0,
				cell = 4,
				set = { tiles = { { name = "a", edges = { "x", "x", "x", "x" }, parts = {} } } },
			})), 0)
			wrong({ center = { 0, 0 } }, "tiles.center")
			wrong({ center = { 1e7, 0, 0 } }, "tiles.center")
			wrong({ cell = 3 }, "tiles.cell")
			wrong({ cell = 257 }, "tiles.cell")
			wrong({ grid = { 12 } }, "tiles.grid")
			wrong({ grid = { 0, 4 } }, "tiles.grid")
			wrong({ grid = { 2.5, 4 } }, "tiles.grid")
			wrong({ grid = { 51, 50 } }, "2500 cells at most")
			wrong({ seed = -1 }, "tiles.seed")
			wrong({ name = 5 }, "tiles.name")
			wrong({ tile = 4 }, "tiles.tile is not a word")
			wrong({ set = 5 }, "tiles.set is")
			wrong({ set = { tiles = {} } }, "tiles.set is")
			wrong(
				set(function(s)
					s.sides = 4
				end),
				"tiles.set.sides"
			)
			wrong(
				set(function(s)
					s.border = "moat"
				end),
				"tiles.set.border is a word some tile has"
			)
			wrong(
				set(function(s)
					s.tiles[2] = 5
				end),
				"tiles.set.tiles[2] is"
			)
			wrong(
				set(function(s)
					s.tiles[2].name = "court"
				end),
				'name "court" is used twice'
			)
			wrong(
				set(function(s)
					s.tiles[2].name = ""
				end),
				"tiles[2].name"
			)
			wrong(
				set(function(s)
					s.tiles[2].edges = { "open", "wall", "open" }
				end),
				"tiles[2].edges"
			)
			wrong(
				set(function(s)
					s.tiles[2].edges = { "open", "wall", "open", 4 }
				end),
				"tiles[2].edges"
			)
			wrong(
				set(function(s)
					s.tiles[2].weight = 0
				end),
				"tiles[2].weight"
			)
			wrong(
				set(function(s)
					s.tiles[2].turns = 2
				end),
				"tiles[2].turns"
			)
			wrong(
				set(function(s)
					s.tiles[2].parts = nil
				end),
				"tiles[2].parts"
			)
			wrong(
				set(function(s)
					s.tiles[2].colour = "red"
				end),
				"tiles[2].colour"
			)
			wrong(
				set(function(s)
					s.tiles[2].parts = { 5 }
				end),
				"tiles[2].parts[1] is"
			)
			wrong(
				set(function(s)
					s.tiles[2].parts = { { size = { 2, 2 }, pos = { 0, 1, 0 }, mat = "stone" } }
				end),
				"parts[1].size"
			)
			wrong(
				set(function(s)
					s.tiles[2].parts = { { size = { 2, 2, 0 }, pos = { 0, 1, 0 }, mat = "stone" } }
				end),
				"parts[1].size"
			)
			wrong(
				set(function(s)
					s.tiles[2].parts = { { size = { 2, 2, 2 }, pos = { 0, 1 }, mat = "stone" } }
				end),
				"parts[1].pos"
			)
			wrong(
				set(function(s)
					s.tiles[2].parts = { { size = { 2, 2, 2 }, pos = { 0, 1, 0 } } }
				end),
				"parts[1].mat"
			)
			wrong(
				set(function(s)
					s.tiles[2].parts = { { size = { 2, 2, 2 }, pos = { 0, 1, 0 }, mat = "stone", rot = 4 } }
				end),
				"parts[1].rot"
			)
			-- a part that reaches over its tile's side would stand in the neighbour
			wrong(
				set(function(s)
					s.tiles[2].parts = { { size = { 8, 2, 2 }, pos = { 5, 1, 0 }, mat = "stone" } }
				end),
				"reaches over the side of its tile"
			)
			check.equal(#Wfc.problems(spec(set(function(s)
				s.tiles[2].parts = { { size = { 8, 2, 2 }, pos = { 4, 1, 0 }, mat = "stone" } }
			end))), 0)
			wrong({ fixed = 5 }, "tiles.fixed is a list")
			wrong({ fixed = { { at = { 13, 1 }, tile = "court" } } }, "fixed[1].at is a cell of the grid")
			wrong({ fixed = { { at = { 1, 1 }, tile = "moat" } } }, 'fixed[1].tile "moat" is no tile')
			wrong({ fixed = { { at = { 1, 1 }, tile = "court", turn = 4 } } }, "fixed[1].turn")
			wrong({ fixed = { { at = { 2, 2 }, tile = "court" }, { at = { 2, 2 }, tile = "wall" } } }, "fixed twice")
			wrong({ fixed = { { at = { 2, 2 }, tile = "court", yaw = 90 } } }, "fixed[1].yaw")
			wrong({ fixed = { { tile = "court" } } }, "fixed[1] is")
			-- a tile that is laid only as written cannot be fixed in a turn
			local stiff = ruin()
			stiff.tiles[2].turns = false
			wrong(
				{ set = stiff, fixed = { { at = { 2, 2 }, tile = "wall", turn = 1 } } },
				'is laid only as written ("turns": false)'
			)
			check.equal(#Wfc.problems(spec({ set = stiff, fixed = { { at = { 2, 2 }, tile = "wall", turn = 0 } } })), 0)
			-- parts written as a table of names, a part's name that is no word, a part wholly under the ground
			wrong(
				set(function(s)
					s.tiles[2].parts = { a = { size = { 2, 2, 2 }, pos = { 0, 1, 0 }, mat = "stone" } }
				end),
				"tiles[2].parts is a list"
			)
			wrong(
				set(function(s)
					s.tiles[2].parts = { { name = 5, size = { 2, 2, 2 }, pos = { 0, 1, 0 }, mat = "stone" } }
				end),
				"parts[1].name"
			)
			wrong(
				set(function(s)
					s.tiles[2].parts = { { size = { 2, 2, 2 }, pos = { 0, -3, 0 }, mat = "stone" } }
				end),
				"wholly under the ground"
			)
			check.equal(#Wfc.problems(spec(set(function(s)
				s.tiles[2].parts = { { size = { 2, 2, 2 }, pos = { 0, -1, 0 }, mat = "stone" } }
			end))), 0)
			check.truthy(#Wfc.problems(5) == 1)
		end)

		test.case("the ways a tile can lie: its quarter turns, clockwise, the same-looking ones once", function()
			local ways = Wfc.ways(ruin())
			local by: { [string]: number } = {}
			local set = ruin()
			for _, w in ways do
				by[set.tiles[w.tile].name] = (by[set.tiles[w.tile].name] or 0) + 1
				-- the words as it lies, against this file's own turning of the list
				for side = 1, 4 do
					check.equal(w.edges[side], shows(set, w, side))
				end
				-- (a tile's weight is shared out over its ways: the tile is taken as often as its weight says)
				check.equal(w.weight, set.tiles[w.tile].weight / 4)
			end
			check.equal(by.court, 4) -- (its words read the same turned; its PARTS turn all the same)
			check.equal(by.wall, 4)
			check.equal(by.corner, 4)
			check.equal(by["end"], 4)
			check.equal(by.tee, 4)
			-- a quarter turn clockwise: what faced north faces east
			local one = Wfc.ways({ tiles = { { name = "gate", edges = { "gate", "a", "b", "c" }, parts = {} } } })
			check.equal(#one, 4)
			check.equal(one[2].turn, 1)
			check.equal(table.concat(one[2].edges, " "), "c gate a b")
			check.equal(table.concat(one[3].edges, " "), "b c gate a")
			check.equal(one[1].weight, 1 / 4) -- (unsaid: 1, over its four ways)
			check.equal(
				Wfc.ways({
					tiles = { { name = "g", edges = { "a", "a", "b", "c" }, weight = 3, turns = false, parts = {} } },
				})[1].weight,
				3
			)
			-- a tile that may not be turned lies one way
			check.equal(#Wfc.ways({
				tiles = { { name = "gate", edges = { "gate", "a", "b", "c" }, turns = false, parts = {} } },
			}), 1)
			-- a point of a tile turns with it: north (0, -1) to east (1, 0) to south to west
			local x, z = Wfc.turned(0, -1, 1)
			check.equal(`{x} {z}`, "1 0")
			x, z = Wfc.turned(0, -1, 2)
			check.equal(`{x} {z}`, "0 1")
			x, z = Wfc.turned(0, -1, 3)
			check.equal(`{x} {z}`, "-1 0")
			x, z = Wfc.turned(3, 5, 0)
			check.equal(`{x} {z}`, "3 5")
			x, z = Wfc.turned(3, 5, 4)
			check.equal(`{x} {z}`, "3 5")
			check.equal(Wfc.edge(ruin(), { tile = 3, turn = 1 }, 3), "wall")
			check.equal(Wfc.edge(ruin(), { tile = 3, turn = 1 }, 4), "wall")
			check.equal(Wfc.edge(ruin(), { tile = 3, turn = 1 }, 1), "open")
		end)

		test.case("the layout: no two neighbours clash, the border shows its word, by this file's own count", function()
			local used: { [string]: number } = {}
			for seed = 1, 60 do
				for _, grid in { { 12, 9 }, { 1, 1 }, { 1, 20 }, { 30, 30 } } do
					if seed <= 8 or grid[1] < 30 then
						local s = spec({ seed = seed, grid = grid })
						local laid, tries = Wfc.solve(s)
						check.truthy(laid ~= nil, tostring(tries))
						local clash, edge = clashes(s, laid)
						check.equal(clash, 0)
						check.equal(edge, 0)
						local c2, e2 = Wfc.clashes(s, laid)
						check.equal(c2 + e2, 0)
						for i = 1, grid[1] do
							for j = 1, grid[2] do
								local name = s.set.tiles[laid[i][j].tile].name
								used[name] = (used[name] or 0) + 1
								check.truthy(laid[i][j].turn >= 0 and laid[i][j].turn <= 3)
							end
						end
					end
				end
			end
			-- every tile of the set is used, the heavier ones more
			check.truthy(used.court > used.corner and used.wall > used["end"])
			for _, name in { "court", "wall", "corner", "end", "tee" } do
				check.truthy(used[name] > 50, name)
			end
			-- the module's own count is a count: a layout spoiled by hand is told
			local s = spec()
			local laid = Wfc.solve(s) :: any
			for i = 1, 12 do
				laid[i][1] = { tile = 2, turn = 1 } -- (walls running north-south along the north border)
			end
			local c, e = Wfc.clashes(s, laid)
			local c1, e1 = clashes(s, laid)
			check.equal(c, c1)
			check.equal(e, e1)
			check.truthy(e >= 12)
			for j = 2, 9 do
				laid[1][j] = { tile = 2, turn = 0 } -- (walls running east-west down the west border)
				laid[2][j] = { tile = 1, turn = 0 } -- (an open court beside each: its west side is open, theirs a wall)
			end
			c, e = Wfc.clashes(s, laid)
			c1, e1 = clashes(s, laid)
			check.equal(c, c1)
			check.equal(e, e1)
			check.truthy(c >= 8)
			-- the same seed, the same layout; another seed, another
			local a, b, other = Wfc.solve(spec()) :: any, Wfc.solve(spec()) :: any, Wfc.solve(spec({ seed = 6 })) :: any
			local differ = 0
			for i = 1, 12 do
				for j = 1, 9 do
					check.equal(a[i][j].tile, b[i][j].tile)
					check.equal(a[i][j].turn, b[i][j].turn)
					differ += if a[i][j].tile == other[i][j].tile and a[i][j].turn == other[i][j].turn then 0 else 1
				end
			end
			check.truthy(differ > 20)
			-- weights: a tile made a hundred times heavier is taken far more often
			local function share(weight: number): number
				local set = ruin()
				set.tiles[1].weight = weight
				local n = 0
				for seed = 1, 10 do
					local g = Wfc.solve(spec({ seed = seed, set = set })) :: any
					for i = 1, 12 do
						for j = 1, 9 do
							n += if g[i][j].tile == 1 then 1 else 0
						end
					end
				end
				return n / (10 * 108)
			end
			check.truthy(share(100) > 0.8)
			check.truthy(share(0.05) < 0.3)
			-- two tiles that fit anything, one nine times as heavy: nine cells in ten are the heavy one
			local two = {
				tiles = {
					{ name = "light", edges = { "x", "x", "x", "x" }, weight = 1, parts = {} },
					{ name = "heavy", edges = { "x", "x", "x", "x" }, weight = 9, parts = {} },
				},
			}
			local heavy = 0
			local g2 = Wfc.solve(spec({ set = two, grid = { 50, 50 } })) :: any
			for i = 1, 50 do
				for j = 1, 50 do
					heavy += if g2[i][j].tile == 2 then 1 else 0
				end
			end
			check.truthy(heavy > 2500 * 0.87 and heavy < 2500 * 0.93, `{heavy} of 2500`)
			-- no border said: the outer sides are free (some layout shows a wall on the grid's edge)
			local free = ruin()
			free.border = nil
			local onEdge = 0
			for seed = 1, 10 do
				local s2 = spec({ seed = seed, set = free })
				local g = Wfc.solve(s2) :: any
				check.equal((clashes(s2, g)), 0)
				for i = 1, 12 do
					onEdge += if shows(free, g[i][1], 1) == "wall" then 1 else 0
				end
			end
			check.truthy(onEdge > 0)
		end)

		test.case("fixed tiles lie where they were put; a set that cannot be laid is said", function()
			local fixed = {
				{ at = { 6, 5 }, tile = "tee", turn = 2 },
				{ at = { 2, 2 }, tile = "corner" },
				{ at = { 12, 9 }, tile = "court" },
			}
			for seed = 1, 20 do
				local s = spec({ seed = seed, fixed = fixed })
				local laid = Wfc.solve(s) :: any
				check.truthy(laid ~= nil)
				check.equal(s.set.tiles[laid[6][5].tile].name, "tee")
				check.equal(laid[6][5].turn, 2)
				check.equal(s.set.tiles[laid[2][2].tile].name, "corner") -- (any turn)
				check.equal(s.set.tiles[laid[12][9].tile].name, "court")
				local clash, edge = clashes(s, laid)
				check.equal(clash + edge, 0)
			end
			-- a fixed tile in a turn its words do not show (they read the same turned): laid, in that turn
			local same = { tiles = { { name = "A", edges = { "a", "a", "a", "a" }, parts = {} } } }
			for turn = 0, 3 do
				local g = Wfc.solve(
					spec({ set = same, grid = { 3, 3 }, fixed = { { at = { 2, 2 }, tile = "A", turn = turn } } })
				)
				check.truthy(g ~= nil)
				check.equal((g :: any)[2][2].turn, turn)
			end
			-- ... and such a tile is laid in all its turns of itself (its parts are seen to turn)
			local turnsSeen: { [number]: boolean } = {}
			local free = Wfc.solve(spec({ set = same, grid = { 10, 10 } })) :: any
			for i = 1, 10 do
				for j = 1, 10 do
					turnsSeen[free[i][j].turn] = true
				end
			end
			check.truthy(turnsSeen[0] and turnsSeen[1] and turnsSeen[2] and turnsSeen[3])
			-- a tile is taken as often as its weight says, however many turns its words show: two tiles of one
			-- weight, one that reads the same turned and one that does not, in a cell either fits
			local fair = {
				tiles = {
					{ name = "court", edges = { "a", "a", "a", "a" }, parts = {} },
					{ name = "gate", edges = { "a", "b", "a", "a" }, parts = {} },
				},
			}
			local courts = 0
			for seed = 1, 600 do
				local g = Wfc.solve(spec({ set = fair, grid = { 1, 1 }, seed = seed })) :: any
				courts += if g[1][1].tile == 1 then 1 else 0
			end
			check.truthy(courts > 240 and courts < 360, `{courts} courts of 600`)
			-- a fixed tile whose outer side does not show the border's word
			local laid, why = Wfc.solve(spec({ fixed = { { at = { 1, 1 }, tile = "tee" } } }))
			check.equal(laid, nil)
			check.truthy(string.find(why, 'the tile fixed at [1, 1] ("tee") cannot lie there', 1, true), why)
			-- two tiles that never fit each other, one of them fixed inside a border of the other's word
			local apart = {
				border = "b",
				tiles = {
					{ name = "a", edges = { "a", "a", "a", "a" }, parts = {} },
					{ name = "b", edges = { "b", "b", "b", "b" }, parts = {} },
				},
			}
			laid, why = Wfc.solve(spec({ set = apart, fixed = { { at = { 6, 5 }, tile = "a" } } }))
			check.equal(laid, nil)
			check.truthy(string.find(why, "the tiles do not fit together on this grid", 1, true), why)
			-- (seen before any tile is chosen: said so, and not begun again - it would come to the same)
			check.truthy(string.find(why, "before any is chosen", 1, true), why)
			check.equal(string.find(why, "begun", 1, true), nil)
			-- a set that fails only AFTER choices: half-dominoes (one side joins a neighbour, three are blank) on a
			-- grid of an odd number of cells - one cell is always left without its half
			local domino = { border = "0", tiles = { { name = "half", edges = { "0", "D", "0", "0" }, parts = {} } } }
			laid, why = Wfc.solve(spec({ set = domino, grid = { 3, 3 } }))
			check.equal(laid, nil)
			check.truthy(string.find(why, "begun 40 times", 1, true), why)
			-- ... and on an even grid it is laid, every half beside its other half
			local s2 = spec({ set = domino, grid = { 4, 4 } })
			local pairs_ = Wfc.solve(s2) :: any
			check.truthy(pairs_ ~= nil)
			check.equal((clashes(s2, pairs_)), 0)
			-- no tile shows the border's word on the right sides at a corner
			local noCorner = { border = "wall", tiles = { tile("wall", { "open", "wall", "open", "wall" }) } }
			laid, why = Wfc.solve(spec({ set = noCorner }))
			check.equal(laid, nil)
			check.truthy(string.find(why, "no tile can lie at [1, 1]", 1, true), why)
			-- a set that often runs into a dead end is begun again and still laid without a clash (walls with no
			-- end piece: every wall must close on itself or run to a tee)
			local hard = {
				border = "open",
				tiles = {
					tile("court", { "open", "open", "open", "open" }, 1),
					tile("wall", { "open", "wall", "open", "wall" }, 3),
					tile("corner", { "open", "wall", "wall", "open" }, 1),
				},
			}
			local again = 0
			for seed = 1, 40 do
				local s = spec({ seed = seed, set = hard, grid = { 10, 10 } })
				local g, tries = Wfc.solve(s)
				check.truthy(g ~= nil, tostring(tries))
				local clash, edge = clashes(s, g)
				check.equal(clash + edge, 0)
				again += if tries > 1 then 1 else 0
			end
			check.truthy(again >= 1, "no layout of the hard set was ever begun again: the test proves nothing of it")
		end)

		test.case(
			"built: each tile's parts turned with it; where two tiles meet on a wall side their walls meet",
			function()
				local s = spec({ center = { 40, 6, -20 } })
				local model, parts, errors, extras = compile(s)
				check.equal(#errors, 0, table.concat(errors, " | "))
				local laid = Wfc.solve(s) :: any
				local t = extras.tiles[1]
				check.equal(t.name, "Ruin")
				check.equal(t.cells, 108)
				-- the parts a layout comes to: a floor a tile, a stub a wall side
				local floors, stubs, sides = 0, 0, 0
				local byCell: { [number]: { any } } = {}
				for _, p in parts do
					local i = math.floor((p.pos[1] - 40 + 96) / 16) + 1
					local j = math.floor((p.pos[3] + 20 + 72) / 16) + 1
					check.truthy(i >= 1 and i <= 12 and j >= 1 and j <= 9)
					byCell[j * 100 + i] = byCell[j * 100 + i] or {}
					table.insert(byCell[j * 100 + i], p)
					if p.name == "Floor" then
						floors += 1
						check.equal(p.pos[2], 5.5) -- (its top on the ground at y = 6)
						check.equal(p.material, "Cobblestone")
					else
						stubs += 1
						check.equal(p.pos[2], 11)
						check.equal(p.material, "Slate")
					end
				end
				check.equal(floors, 108)
				local count: { [string]: number } = {}
				for i = 1, 12 do
					for j = 1, 9 do
						count[s.set.tiles[laid[i][j].tile].name] = (count[s.set.tiles[laid[i][j].tile].name] or 0) + 1
						local cx, cz = 40 - 96 + (i - 0.5) * 16, -20 - 72 + (j - 0.5) * 16
						for side, dir in { { 0, -1 }, { 1, 0 }, { 0, 1 }, { -1, 0 } } do
							if shows(s.set, laid[i][j], side) == "wall" then
								sides += 1
								-- a stub of this cell reaches from its middle to that side: its box, as turned
								local found = false
								for _, p in byCell[j * 100 + i] do
									if p.name == "Wall" then
										-- (the part's own x and z extents after its turn: rot's columns are its axes)
										local ex = math.abs(p.rot[1][1]) * p.size[1] / 2
											+ math.abs(p.rot[1][3]) * p.size[3] / 2
										local ez = math.abs(p.rot[3][1]) * p.size[1] / 2
											+ math.abs(p.rot[3][3]) * p.size[3] / 2
										local reach = (p.pos[1] - cx) * dir[1]
											+ (p.pos[3] - cz) * dir[2]
											+ (if dir[1] ~= 0 then ex else ez)
										local across = math.abs((p.pos[1] - cx) * dir[2])
											+ math.abs((p.pos[3] - cz) * dir[1])
										if math.abs(reach - 8) < 1e-6 and across < 1e-6 then
											found = true
											-- long way along the side's direction, thin across it
											check.truthy(math.abs((if dir[1] ~= 0 then ex else ez) - 4) < 1e-6)
											check.truthy(math.abs((if dir[1] ~= 0 then ez else ex) - 1) < 1e-6)
										end
									end
								end
								check.truthy(found, `no wall to side {side} of [{i}, {j}]`)
							end
						end
					end
				end
				check.equal(stubs, sides) -- (and no stub where no side says wall)
				for name, n in count do
					check.equal(t.count[name], n)
				end
				check.equal(t.tries, select(2, Wfc.solve(s)))
				-- all of it in the model the game loads
				local held = 0
				for _, c in model.Children do
					if c.Name == "Ruin" then
						held = #c.Children
					end
				end
				check.equal(held, #parts)
				-- a part's own name is kept; one with none takes its tile's
				local named = ruin()
				named.tiles[1].parts = { { size = { 4, 4, 4 }, pos = { 0, 2, 0 }, mat = "stone" } }
				local _, plain =
					compile(spec({ set = named, grid = { 2, 2 }, fixed = { { at = { 1, 1 }, tile = "court" } } }))
				local courts = 0
				for _, p in plain do
					courts += if p.name == "court" then 1 else 0
				end
				check.truthy(courts >= 1)
			end
		)

		test.case("the compiler: what cannot be laid is said", function()
			local function wrong(more: any, text: string)
				local _, parts, errors = compile(spec(more))
				check.equal(#parts, 0)
				check.truthy(#errors >= 1)
				check.truthy(string.find(table.concat(errors, " | "), text, 1, true), table.concat(errors, " | "))
			end
			wrong({ cell = 2 }, "tiles.cell")
			wrong({ fixed = { { at = { 1, 1 }, tile = "tee" } } }, "cannot lie there")
			local noCorner = { border = "wall", tiles = { tile("wall", { "open", "wall", "open", "wall" }) } }
			wrong({ set = noCorner }, "no tile can lie at [1, 1]")
			-- an unknown step is told of tiles
			local _, _, issues = World.compile({ name = "T", palette = PALETTE, build = { { tile = spec() } } })
			check.truthy(string.find(issues[1].message, "| tiles |", 1, true))
		end)
	end)
end
