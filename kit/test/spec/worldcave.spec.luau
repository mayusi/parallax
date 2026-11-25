-- worldcave.spec.luau (kit) — A CAVE GROWN BY A CELLULAR AUTOMATON (kit/lib/worldcave.luau; the owner's method list:
-- "Cellular automata generation"). The rule is held to hand-made grids; the plan to what a cave a body can use must
-- be - one piece of floor, no passage under two cells, no two pieces touching by a corner - each counted here by
-- its own walk, not by the module's; and the parts the compiler makes of it are FLOODED on a half-stud grid.
-- Not claimed here: that a cave looks like a cave. That is a built world, looked at.
local frk = require("../frk")
local test, check = frk.test, frk.check

local Cave = require("../../lib/worldcave")
local World = require("../../lib/world")

local PALETTE = {
	rock = { material = "Slate", color = { 70, 68, 66 } },
	dirt = { material = "Ground", color = { 90, 80, 66 } },
}

local function spec(more: any?): any
	local s: any =
		{ name = "Grotto", center = { 0, 0, 0 }, area = { 240, 200 }, seed = 4, mat = "rock", floor = "dirt" }
	for k, v in more or {} do
		s[k] = v
	end
	return s
end

local function compile(s: any): (any, { any }, { string }, { string }, any)
	local model, parts, issues, extras =
		World.compile({ name = "T", scale = "r6", palette = PALETTE, build = { { cave = s } } })
	local errors, warns = {}, {}
	for _, i in issues do
		table.insert(if i.severity == "error" then errors else warns, i.message)
	end
	return model, parts, errors, warns, extras
end

local function grid(rows: { string }): ({ { boolean } }, number, number)
	local nz, nx = #rows, #rows[1]
	local g: { { boolean } } = table.create(nx)
	for i = 1, nx do
		g[i] = table.create(nz, false)
		for j = 1, nz do
			g[i][j] = string.sub(rows[j], i, i) == "#"
		end
	end
	return g, nx, nz
end

-- the floor's pieces (joined by a side), counted by a walk of this file's own
local function pieces(plan: any): (number, number)
	local seen: { [number]: boolean } = {}
	local n, cells = 0, 0
	for i = 1, plan.nx do
		for j = 1, plan.nz do
			if plan.kind[i][j] ~= 0 then
				cells += 1
				if not seen[j * 1000 + i] then
					n += 1
					local stack = { j * 1000 + i }
					seen[j * 1000 + i] = true
					while #stack > 0 do
						local at = table.remove(stack) :: number
						for _, d in { 1, -1, 1000, -1000 } do
							local a, b = (at + d) % 1000, (at + d) // 1000
							if
								a >= 1
								and a <= plan.nx
								and b >= 1
								and b <= plan.nz
								and plan.kind[a][b] ~= 0
								and not seen[at + d]
							then
								seen[at + d] = true
								table.insert(stack, at + d)
							end
						end
					end
				end
			end
		end
	end
	return n, cells
end

-- A BODY 8 STUDS WIDE (a square of 2 x 2 cells), set on the first square of floor and slid one cell at a time, by a
-- walk of this file's own -> how many floor cells it never stands on
local function unslid(plan: any): number
	local function stands(i: number, j: number): boolean
		return i >= 1
			and j >= 1
			and i < plan.nx
			and j < plan.nz
			and plan.kind[i][j] == 1
			and plan.kind[i + 1][j] == 1
			and plan.kind[i][j + 1] == 1
			and plan.kind[i + 1][j + 1] == 1
	end
	local stood: { [number]: boolean } = {}
	local seen: { [number]: boolean } = {}
	local first
	for i = 1, plan.nx do
		for j = 1, plan.nz do
			if not first and stands(i, j) then
				first = { i, j }
			end
		end
	end
	local stack = if first then { first } else {}
	if first then
		seen[first[2] * 1000 + first[1]] = true
	end
	while #stack > 0 do
		local at = table.remove(stack) :: { number }
		for _, d in { { 0, 0 }, { 1, 0 }, { 0, 1 }, { 1, 1 } } do
			stood[(at[2] + d[2]) * 1000 + at[1] + d[1]] = true
		end
		for _, d in { { 1, 0 }, { -1, 0 }, { 0, 1 }, { 0, -1 } } do
			local a, b = at[1] + d[1], at[2] + d[2]
			if stands(a, b) and not seen[b * 1000 + a] then
				seen[b * 1000 + a] = true
				table.insert(stack, { a, b })
			end
		end
	end
	local never = 0
	for i = 1, plan.nx do
		for j = 1, plan.nz do
			if plan.kind[i][j] == 1 and not stood[j * 1000 + i] then
				never += 1
			end
		end
	end
	return never
end

-- the compiled walls on a half-stud grid, and a flood through what is not wall (the eight neighbours: a corner
-- left open between two walls is a way out) -> did it get out of the grid, how many of the places asked it reached
local STEP = 0.5
local function flood(parts: { any }, from: { number }, ask: { { number } }): (boolean, number)
	local lo, hi = -220, 220
	local n = math.floor((hi - lo) / STEP)
	local wall: { [number]: boolean } = {}
	local function cellOf(v: number): number
		return math.floor((v - lo) / STEP)
	end
	for _, p in parts do
		if p.name == "Wall" then
			local x0, x1 = p.pos[1] - p.size[1] / 2, p.pos[1] + p.size[1] / 2
			local z0, z1 = p.pos[3] - p.size[3] / 2, p.pos[3] + p.size[3] / 2
			for x = cellOf(x0), cellOf(x1) do
				for z = cellOf(z0), cellOf(z1) do
					local mx, mz = lo + (x + 0.5) * STEP, lo + (z + 0.5) * STEP
					if mx > x0 and mx < x1 and mz > z0 and mz < z1 then
						wall[z * n + x] = true
					end
				end
			end
		end
	end
	local seen: { [number]: boolean } = {}
	local sx, sz = cellOf(from[1]), cellOf(from[2])
	local stack = { { sx, sz } }
	seen[sz * n + sx] = true
	local out = false
	while #stack > 0 do
		local at = table.remove(stack) :: { number }
		for _, d in { { 1, 0 }, { -1, 0 }, { 0, 1 }, { 0, -1 }, { 1, 1 }, { 1, -1 }, { -1, 1 }, { -1, -1 } } do
			local x, z = at[1] + d[1], at[2] + d[2]
			if x < 0 or x >= n or z < 0 or z >= n then
				out = true
			elseif not wall[z * n + x] and not seen[z * n + x] then
				seen[z * n + x] = true
				table.insert(stack, { x, z })
			end
		end
	end
	local reached = 0
	for _, a in ask do
		if seen[cellOf(a[2]) * n + cellOf(a[1])] then
			reached += 1
		end
	end
	return out, reached
end

return function()
	test.suite("A cave grown by a cellular automaton", function()
		test.case("what is wrong with a cave is said", function()
			local function wrong(more: any, text: string)
				local problems = Cave.problems(spec(more))
				check.truthy(#problems >= 1)
				check.truthy(string.find(table.concat(problems, " | "), text, 1, true), table.concat(problems, " | "))
			end
			check.equal(#Cave.problems(spec()), 0)
			check.equal(
				#Cave.problems(
					spec({ roof = "rock", start = true, fill = 0.3, turns = 8, height = 60, thickness = 0.5, seed = 0 })
				),
				0
			)
			check.equal(#Cave.problems(spec({ fill = 0.5, turns = 1, height = 12, thickness = 2, seed = 65535 })), 0)
			wrong({ area = { 60, 200 } }, "cave.area")
			wrong({ area = { 200, 801 } }, "cave.area")
			wrong({ area = "big" }, "cave.area")
			wrong({ center = { 0, 0 } }, "cave.center")
			wrong({ seed = 1.5 }, "cave.seed")
			wrong({ seed = 65536 }, "cave.seed")
			wrong({ fill = 0.29 }, "cave.fill")
			wrong({ fill = 0.51 }, "cave.fill") -- (over a half the automaton closes nearly every cave)
			wrong({ fill = "half" }, "cave.fill")
			wrong({ turns = 0 }, "cave.turns")
			wrong({ turns = 9 }, "cave.turns")
			wrong({ turns = 2.5 }, "cave.turns")
			wrong({ height = 11 }, "cave.height is 12 to 60")
			wrong({ height = 61 }, "cave.height")
			wrong({ thickness = 0.4 }, "cave.thickness")
			wrong({ thickness = 3 }, "cave.thickness")
			wrong({ roof = true }, "cave.roof is a palette entry's name")
			wrong({ mat = 5 }, "cave.mat is a palette entry's name")
			wrong({ start = "yes" }, "cave.start is true or false")
			wrong({ rooms = 4 }, "cave.rooms")
			wrong({ rooms = 4 }, "start, stream, landmark)")
			wrong({ name = 5 }, "cave.name")
			wrong({ name = "" }, "cave.name")
			wrong({ area = { 200, 200, 200 } }, "cave.area")
			wrong({ center = { 0, 0, 0, 0 } }, "cave.center")
			wrong({ center = { 1e7, 0, 0 } }, "within a million studs")
			wrong({ center = { 0, 0, -1e300 } }, "within a million studs")
			check.equal(#Cave.problems(spec({ center = { 1e6, -1e6, 0 }, stream = true, landmark = true })), 0)
			check.truthy(#Cave.problems(5) == 1)
			-- what is unsaid, and when a cave has closed up
			check.equal(Cave.DEFAULTS.fill, 0.45)
			check.equal(Cave.DEFAULTS.turns, 4)
			check.equal(Cave.DEFAULTS.height, 12)
			check.equal(Cave.DEFAULTS.thickness, 1)
			check.equal(Cave.LEAST, 0.12)
		end)

		test.case("the rule: a cell is rock when five or more of the nine cells round it are rock", function()
			-- a lone rock in the open goes; a lone hole in rock closes
			local g, nx, nz = grid({ ".....", ".....", "..#..", ".....", "....." })
			local out = Cave.turn(g, nx, nz)
			check.equal(out[3][3], false)
			g, nx, nz = grid({ "#####", "#####", "##.##", "#####", "#####" })
			check.equal(Cave.turn(g, nx, nz)[3][3], true)
			-- exactly four of nine: open; exactly five: rock (the middle cell of each)
			g, nx, nz = grid({ ".....", ".##..", ".##..", ".#...", "....." })
			check.equal(Cave.turn(g, nx, nz)[2][3], true) -- (five of nine, itself rock)
			g, nx, nz = grid({ ".....", ".##..", ".....", ".##..", "....." })
			check.equal(Cave.turn(g, nx, nz)[2][3], false) -- (four of nine)
			g, nx, nz = grid({ ".....", ".##..", "..#..", ".##..", "....." })
			check.equal(Cave.turn(g, nx, nz)[2][3], true) -- (five of nine, itself open)
			check.equal(Cave.turn(g, nx, nz)[4][3], false) -- (three of nine)
			-- off the grid counts as rock: an open corner cell has five rock neighbours there already
			g, nx, nz = grid({ "...", "...", "..." })
			out = Cave.turn(g, nx, nz)
			check.equal(out[1][1], true)
			check.equal(out[2][1], false) -- (an edge cell: three off the grid)
			check.equal(out[2][2], false)
			-- the turn makes a new grid and leaves the old one as it was
			check.equal(g[1][1], false)
		end)

		test.case(
			"the plan: one piece of floor, no passage under two cells, no corners touching, rock all round",
			function()
				local closed, pockets, opened = 0, 0, 0
				for seed = 1, 50 do
					for _, fill in { 0.35, 0.45, 0.5 } do
						local plan = Cave.plan(spec({ seed = seed, fill = fill }))
						local n, cells = pieces(plan)
						check.equal(cells, plan.cells)
						check.truthy(n <= 1, `{n} pieces of floor (seed {seed}, fill {fill})`)
						check.equal(plan.share, cells / (plan.nx * plan.nz))
						for i = 1, plan.nx do
							check.equal(plan.kind[i][1] + plan.kind[i][plan.nz], 0)
						end
						for j = 1, plan.nz do
							check.equal(plan.kind[1][j] + plan.kind[plan.nx][j], 0)
						end
						local function floor(i: number, j: number): boolean
							return plan.kind[i] ~= nil and plan.kind[i][j] == 1
						end
						for i = 1, plan.nx do
							for j = 1, plan.nz do
								if floor(i, j) then
									-- in a square of 2 x 2 floor (8 studs: a doorway on the rig's sheet)
									local wide = false
									for oi = i - 1, i do
										for oj = j - 1, j do
											wide = wide
												or (
													floor(oi, oj)
													and floor(oi + 1, oj)
													and floor(oi, oj + 1)
													and floor(oi + 1, oj + 1)
												)
										end
									end
									check.truthy(wide, `a passage one cell wide at {i},{j} (seed {seed}, fill {fill})`)
									-- no floor across a corner with rock on both sides of it
									if floor(i + 1, j + 1) then
										check.truthy(floor(i + 1, j) or floor(i, j + 1))
									end
									if floor(i - 1, j + 1) then
										check.truthy(floor(i - 1, j) or floor(i, j + 1))
									end
								end
							end
						end
						-- a body 8 studs wide gets everywhere: by the module's measure and by this file's own slide
						local bodies, thin = Cave.wide(plan)
						check.equal(thin, 0)
						check.equal(bodies, if cells > 0 then 1 else 0)
						check.equal(unslid(plan), 0)
						check.equal(Cave.pinches(plan), 0)
						-- the bookkeeping: what the automaton left open, less what was closed, plus what was opened
						local raw = Cave.raw(spec({ seed = seed, fill = fill }))
						local open = 0
						for i = 1, plan.nx do
							for j = 1, plan.nz do
								open += if raw[i][j] then 0 else 1
							end
						end
						check.equal(cells, open - plan.closed - plan.pockets + plan.opened)
						closed += if plan.closed > 0 then 1 else 0
						pockets += if plan.pockets > 0 then 1 else 0
						opened += if plan.opened > 0 then 1 else 0
					end
				end
				-- each mending rule had work to do (or these checks prove nothing about it)
				check.truthy(closed >= 20 and pockets >= 20 and opened >= 3, `{closed} {pockets} {opened}`)
				-- the same seed is the same cave; another seed is another
				local a, b, c = Cave.plan(spec()), Cave.plan(spec()), Cave.plan(spec({ seed = 5 }))
				local same, differ = 0, 0
				for i = 1, a.nx do
					for j = 1, a.nz do
						same += if a.kind[i][j] == b.kind[i][j] then 0 else 1
						differ += if a.kind[i][j] == c.kind[i][j] then 0 else 1
					end
				end
				check.equal(same, 0)
				check.truthy(differ > 300)
				-- more rock asked, less floor (over many seeds); more turns, smoother (fewer wall runs for the floor)
				local wide, narrow = 0, 0
				for seed = 1, 20 do
					wide += Cave.plan(spec({ seed = seed, fill = 0.35 })).cells
					narrow += Cave.plan(spec({ seed = seed, fill = 0.5 })).cells
				end
				check.truthy(wide > narrow * 1.5)
			end
		)

		test.case("the mending rules, each on a grid made by hand", function()
			-- (Cave.plan reads the automaton's grid; here the three rules are asked of what they leave, through the
			-- two measures a plan is held to)
			local function plan(rows: { string }): any
				local g, nx, nz = grid(rows)
				local kind: { { number } } = table.create(nx)
				for i = 1, nx do
					kind[i] = table.create(nz, 0)
					for j = 1, nz do
						kind[i][j] = if g[i][j] then 0 else 1
					end
				end
				return { nx = nx, nz = nz, kind = kind }
			end
			local function wide(rows: { string }): string
				local bodies, thin = Cave.wide(plan(rows))
				return `{bodies} {thin}`
			end
			check.equal(wide({ "####", "#..#", "#..#", "####" }), "1 0")
			check.equal(wide({ "#####", "#..##", "#...#", "#####" }), "1 1") -- (one cell sticks out)
			check.equal(wide({ "######", "#....#", "######" }), "0 4") -- (a passage one cell wide)
			check.equal(wide({ "####", "####" }), "0 0")
			-- two chambers joined by a neck one cell wide: two groups, the neck thin
			check.equal(wide({ "########", "#..##..#", "#......#", "########" }), "2 2")
			-- two chambers that meet along ONE cell's side (a squeeze 4 studs wide between two rock corners): every
			-- cell lies in a square, and still a body 8 studs wide does not get through
			check.equal(wide({ "#####", "#..##", "#..##", "##..#", "##..#", "#####" }), "2 0")
			check.equal(unslid(plan({ "#####", "#..##", "#..##", "##..#", "##..#", "#####" })), 4)
			-- ... offset by one more cell they share a square's width: one group
			check.equal(wide({ "#####", "#..##", "#...#", "#...#", "##..#", "#####" }), "1 0")
			check.equal(Cave.pinches(plan({ "####", "#..#", "#..#", "####" })), 0)
			check.equal(Cave.pinches(plan({ "#####", "#.###", "##.##", "#####" })), 1)
			check.equal(Cave.pinches(plan({ "#####", "##.##", "#.###", "#####" })), 1) -- (the other diagonal)
			check.equal(Cave.pinches(plan({ "#####", "#..##", "##..#", "#####" })), 0) -- (joined by a side)
			-- opening: the two rock cells of a corner-touching square become floor, and one more beside them, so
			-- that the new square is one slide from a square the floor has
			local one = plan({ "######", "#..###", "#..###", "###..#", "###..#", "######" })
			check.equal(Cave.pinches(one), 1)
			check.equal(wide({ "######", "#..###", "#..###", "###..#", "###..#", "######" }), "2 0")
			check.equal(Cave.open(one.kind, one.nx, one.nz), 4)
			check.equal(one.kind[4][3] + one.kind[3][4] + one.kind[2][4] + one.kind[5][3], 4)
			check.equal(Cave.pinches(one), 0)
			local bodies, thin = Cave.wide(one)
			check.equal(`{bodies} {thin}`, "1 0")
			check.equal(unslid(one), 0)
			-- the other diagonal
			local other = plan({ "######", "###..#", "###..#", "#..###", "#..###", "######" })
			check.equal(Cave.pinches(other), 1)
			check.equal(Cave.open(other.kind, other.nx, other.nz), 4)
			check.equal(Cave.pinches(other), 0)
			bodies, thin = Cave.wide(other)
			check.equal(`{bodies} {thin}`, "1 0")
			check.equal(unslid(other), 0)
			-- an opening that makes another BEHIND the sweep: opened too (a second sweep)
			local two = plan({ "########", "#.######", "####.###", "###.####", "########", "########" })
			check.equal(Cave.pinches(two), 1)
			check.equal(Cave.open(two.kind, two.nx, two.nz), 7)
			check.equal(Cave.pinches(two), 0)
			-- ... and the same from the other diagonal's rule
			local three = plan({ "########", "#.#.####", "####.###", "########", "########", "########" })
			check.equal(Cave.open(three.kind, three.nx, three.nz), 6)
			check.equal(Cave.pinches(three), 0)
			-- the outermost ring is never opened
			local edge = plan({ "#####", "#.###", "##.##", "#####" })
			Cave.open(edge.kind, edge.nx, edge.nz)
			for i = 1, edge.nx do
				check.equal(edge.kind[i][1] + edge.kind[i][edge.nz], 0)
			end
			for j = 1, edge.nz do
				check.equal(edge.kind[1][j] + edge.kind[edge.nx][j], 0)
			end
			-- nothing to open, nothing changed
			local none = plan({ "####", "#..#", "#..#", "####" })
			check.equal(Cave.open(none.kind, none.nx, none.nz), 0)
			-- the automaton's turns: one more turn asked is the rule run once more on the same grid
			for _, turns in { 1, 3 } do
				local before, nx, nz = Cave.raw(spec({ turns = turns }))
				local after = Cave.raw(spec({ turns = turns + 1 }))
				local by = Cave.turn(before, nx, nz)
				local differ, moved = 0, 0
				for i = 1, nx do
					for j = 1, nz do
						differ += if by[i][j] == after[i][j] then 0 else 1
						moved += if before[i][j] == after[i][j] then 0 else 1
					end
				end
				check.equal(differ, 0)
				check.truthy(moved > 0)
			end
			local four, nx4, nz4 = Cave.raw(spec({ turns = 4 }))
			local unsaid = Cave.raw(spec())
			for i = 1, nx4 do
				for j = 1, nz4 do
					check.equal(four[i][j], unsaid[i][j]) -- (four turns unless said)
				end
			end
			-- the outermost ring is rock after every number of turns, at the widest fill
			for turns = 1, 8 do
				local raw, nx, nz = Cave.raw(spec({ turns = turns, fill = 0.3, seed = turns }))
				for i = 1, nx do
					check.truthy(raw[i][1] and raw[i][nz])
				end
				for j = 1, nz do
					check.truthy(raw[1][j] and raw[nx][j])
				end
			end
		end)

		test.case("the start is in the widest chamber, the far place the longest walk from it", function()
			for seed = 1, 25 do
				local plan = Cave.plan(spec({ seed = seed }))
				local function floor(i: number, j: number): boolean
					return plan.kind[i] ~= nil and plan.kind[i][j] == 1
				end
				-- the largest square of floor, by this file's own count (every low corner, every side)
				local function square(i: number, j: number, n: number): boolean
					for a = i, i + n - 1 do
						for b = j, j + n - 1 do
							if not floor(a, b) then
								return false
							end
						end
					end
					return true
				end
				local most = 0
				for i = 1, plan.nx do
					for j = 1, plan.nz do
						while square(i, j, most + 1) do
							most += 1
						end
					end
				end
				check.equal(plan.side, most)
				check.truthy(plan.side >= 2)
				-- the start is the middle of a square of floor that wide
				local lowI, lowJ = plan.start[1] - plan.side / 2 + 1, plan.start[2] - plan.side / 2 + 1
				check.equal(lowI % 1, 0)
				check.equal(lowJ % 1, 0)
				check.truthy(square(lowI, lowJ, plan.side))
				-- the walk starts from a cell of that square
				check.truthy(plan.from[1] >= lowI and plan.from[1] < lowI + plan.side)
				check.truthy(plan.from[2] >= lowJ and plan.from[2] < lowJ + plan.side)
				-- the walk, by rounds of this file's own
				local steps: { [number]: number } = { [plan.from[2] * 1000 + plan.from[1]] = 0 }
				local round, n, longest = { plan.from }, 0, 0
				while #round > 0 do
					local nextRound = {}
					for _, q in round do
						for _, d in { { 1, 0 }, { -1, 0 }, { 0, 1 }, { 0, -1 } } do
							local a, b = q[1] + d[1], q[2] + d[2]
							if floor(a, b) and steps[b * 1000 + a] == nil then
								steps[b * 1000 + a] = n + 1
								longest = n + 1
								table.insert(nextRound, { a, b })
							end
						end
					end
					n += 1
					round = nextRound
				end
				check.equal(plan.walk, longest)
				check.equal(steps[plan.far[2] * 1000 + plan.far[1]], longest)
				check.truthy(longest >= 20)
			end
		end)

		test.case("built: a body let loose at the start never gets out, and gets to every cell of the floor", function()
			for _, more in
				{
					{ seed = 4 },
					{ seed = 9, fill = 0.4, thickness = 2 },
					{ seed = 17, fill = 0.5, area = { 320, 280 } },
					{ seed = 31, center = { 40, 10, -30 }, thickness = 0.5, turns = 2 },
					{ seed = 2, area = { 64, 64 }, fill = 0.35 },
				} :: { any }
			do
				local s = spec(more)
				local plan = Cave.plan(s)
				local _, parts, errors, warns, extras = compile(s)
				check.equal(#errors, 0, table.concat(errors, " | "))
				for _, w in warns do
					check.equal(string.find(w, "z-fighting", 1, true), nil, w) -- (no two walls in one place)
					check.equal(string.find(w, "coplanar", 1, true), nil, w)
				end
				local cave = extras.caves[1]
				local ask = {}
				local ox, oz = s.center[1] - plan.nx * 2, s.center[3] - plan.nz * 2
				for i = 1, plan.nx do
					for j = 1, plan.nz do
						if plan.kind[i][j] == 1 then
							table.insert(ask, { ox + (i - 0.5) * 4, oz + (j - 0.5) * 4 })
						end
					end
				end
				check.equal(#ask, plan.cells)
				local out, reached = flood(parts, { cave.start[1], cave.start[3] }, ask)
				check.equal(out, false)
				check.equal(reached, #ask)
				-- the middle of a rock cell is NOT reached (the flood is not let through the walls): every rock cell
				-- that has no floor beside it, even by a corner
				local rockAsk = {}
				for i = 2, plan.nx - 1 do
					for j = 2, plan.nz - 1 do
						local solid = true
						for a = i - 1, i + 1 do
							for b = j - 1, j + 1 do
								solid = solid and plan.kind[a][b] == 0
							end
						end
						if solid then
							table.insert(rockAsk, { ox + (i - 0.5) * 4, oz + (j - 0.5) * 4 })
						end
					end
				end
				local _, inRock = flood(parts, { cave.start[1], cave.start[3] }, rockAsk)
				check.equal(inRock, 0)
				-- no wall stands on the floor
				for _, w in parts do
					if w.name == "Wall" then
						for _, f in parts do
							if f.name == "CaveFloor" then
								local overX = math.min(w.pos[1] + w.size[1] / 2, f.pos[1] + f.size[1] / 2)
									- math.max(w.pos[1] - w.size[1] / 2, f.pos[1] - f.size[1] / 2)
								local overZ = math.min(w.pos[3] + w.size[3] / 2, f.pos[3] + f.size[3] / 2)
									- math.max(w.pos[3] - w.size[3] / 2, f.pos[3] - f.size[3] / 2)
								check.truthy(overX <= 1e-6 or overZ <= 1e-6)
							end
						end
					end
				end
			end
		end)

		test.case("the compiler: floor, walls, a roof and a start; all of it in the model the game loads", function()
			local s = spec({ roof = "rock", start = true, height = 14, center = { 10, 6, -20 } })
			local plan = Cave.plan(s)
			local model, parts, errors, _, extras = compile(s)
			check.equal(#errors, 0)
			local count: { [string]: number } = {}
			local spawn
			local floorArea = 0
			for _, p in parts do
				count[p.name] = (count[p.name] or 0) + 1
				if p.name == "Spawn" then
					spawn = p
				elseif p.name == "CaveFloor" then
					floorArea += p.size[1] * p.size[3]
					check.equal(p.pos[2] + p.size[2] / 2, 6)
				elseif p.name == "Wall" then
					check.equal(p.pos[2] - p.size[2] / 2, 6)
					check.equal(p.size[2], 14)
				elseif p.name == "Roof" then
					check.equal(p.pos[2] - p.size[2] / 2, 20)
				end
			end
			check.truthy(count.CaveFloor >= 20 and count.Wall >= 60)
			check.equal(count.Roof, count.CaveFloor) -- (a slab over every piece of floor)
			check.equal(count.Spawn, 1)
			check.equal(count.DungeonFloor, nil)
			check.equal(floorArea, plan.cells * 16) -- (the floor is covered once)
			local cave = extras.caves[1]
			check.equal(cave.name, "Grotto")
			-- the start: the middle of the plan's start cell, on the floor; the spawn pad lies on it
			check.equal(cave.start[1], 10 - plan.nx * 2 + plan.start[1] * 4)
			check.equal(cave.start[3], -20 - plan.nz * 2 + plan.start[2] * 4)
			check.equal(cave.start[2], 6)
			check.equal(cave.far[1], 10 - plan.nx * 2 + (plan.far[1] - 0.5) * 4)
			check.equal(cave.far[3], -20 - plan.nz * 2 + (plan.far[2] - 0.5) * 4)
			check.equal(spawn.pos[1], cave.start[1])
			check.equal(spawn.pos[2], 6.5)
			check.equal(spawn.pos[3], cave.start[3])
			check.truthy(spawn.spawn == true)
			check.equal(spawn.class, "SpawnLocation")
			check.equal(`{spawn.size[1]} {spawn.size[2]} {spawn.size[3]}`, "6 1 6")
			check.equal(spawn.material, "Ground")
			local m = cave.measure
			check.equal(m.floor, plan.cells * 16)
			check.equal(m.share, plan.share)
			check.equal(m.walk, plan.walk * 4)
			check.equal(m.chamber, plan.side * 4)
			check.equal(m.closed, plan.closed)
			check.equal(m.pockets, plan.pockets)
			check.equal(m.opened, plan.opened)
			-- the widest chamber claims its ceiling: a square that is floor all over, 14 high
			local ceilings = 0
			for _, f in extras.fits do
				if f.kind == "ceiling" then
					ceilings += 1
					check.equal(f.size[1], m.chamber)
					check.equal(f.size[2], 14)
					check.equal(f.size[3], m.chamber)
					check.equal(f.pos[1], cave.start[1])
					check.equal(f.pos[2], 13)
					check.equal(f.pos[3], cave.start[3])
					for i = plan.start[1] - plan.side / 2 + 1, plan.start[1] + plan.side / 2 do
						for j = plan.start[2] - plan.side / 2 + 1, plan.start[2] + plan.side / 2 do
							check.equal(plan.kind[i][j], 1)
						end
					end
				end
			end
			check.equal(ceilings, 1)
			local held = 0
			for _, c in model.Children do
				if c.Name == "Grotto" then
					held = #c.Children
				end
			end
			check.equal(held, #parts)
			-- no roof, no start: neither part, no ceiling claimed
			local _, bare, _, _, open = compile(spec())
			for _, p in bare do
				check.truthy(p.name ~= "Roof" and p.name ~= "Spawn")
			end
			for _, f in open.fits do
				check.truthy(f.kind ~= "ceiling")
			end
		end)

		test.case(
			"built as asked: the walls' thickness and stuff, inside the area, the spawn's pad on the floor",
			function()
				-- walls as thick as said, of the wall's stuff; floors of the floor's
				for _, t in { 0.5, 1, 2 } do
					local _, parts, errors = compile(spec({ thickness = t, seed = 6 }))
					check.equal(#errors, 0)
					local walls = 0
					for _, p in parts do
						if p.name == "Wall" then
							walls += 1
							check.truthy(
								p.size[1] == t or p.size[3] == t,
								`a wall {p.size[1]} by {p.size[3]} of thickness {t}`
							)
							check.equal(p.material, "Slate")
						elseif p.name == "CaveFloor" then
							check.equal(p.material, "Ground")
							check.equal(p.size[2], 1)
						end
					end
					check.truthy(walls > 50)
				end
				-- an area that is no multiple of 4, a centre off the grid: nothing built outside the area asked
				for _, area in { { 66, 70 }, { 242, 198 }, { 64, 203 } } do
					local s =
						spec({ area = area, center = { 13.5, 2, -7.25 }, thickness = 2, fill = 0.35, roof = "rock" })
					local _, parts, errors = compile(s)
					check.equal(#errors, 0)
					check.truthy(#parts > 10)
					for _, p in parts do
						check.truthy(math.abs(p.pos[1] - 13.5) + p.size[1] / 2 <= area[1] / 2 + 1e-9, p.name)
						check.truthy(math.abs(p.pos[3] + 7.25) + p.size[3] / 2 <= area[2] / 2 + 1e-9, p.name)
					end
				end
				-- the spawn's pad lies wholly on the floor, in the smallest caves too (it stuck into a wall where the
				-- widest chamber was one cell); and the smallest chamber there is is 8 studs
				local built, least = 0, math.huge
				for seed = 1, 400 do
					for _, turns in { 1, 2 } do
						local s = spec({ area = { 64, 64 }, seed = seed, turns = turns, fill = 0.5 })
						local plan = Cave.plan(s)
						if plan.share >= Cave.LEAST then
							built += 1
							least = math.min(least, plan.side)
							for _, d in { { -0.74, -0.74 }, { 0.74, -0.74 }, { -0.74, 0.74 }, { 0.74, 0.74 } } do
								-- (the pad reaches 3 studs = 0.75 cells each way from the start)
								local i = math.floor(plan.start[1] + d[1]) + 1
								local j = math.floor(plan.start[2] + d[2]) + 1
								check.equal(plan.kind[i][j], 1, `seed {seed} turns {turns}`)
							end
						end
					end
				end
				check.truthy(built > 100)
				check.equal(least, 2)
				-- ... and as built: the pad's box clear of every wall
				-- (the first small cave whose widest chamber is the least there is: 8 studs)
				local tight
				for seed = 1, 400 do
					local plan = Cave.plan(spec({ area = { 64, 64 }, seed = seed, turns = 1, fill = 0.5 }))
					if not tight and plan.share >= Cave.LEAST and plan.side == 2 then
						tight = seed
					end
				end
				check.truthy(tight ~= nil)
				local s = spec({ area = { 64, 64 }, seed = tight, turns = 1, fill = 0.5, start = true, roof = "rock" })
				local _, parts, errors = compile(s)
				check.equal(#errors, 0)
				local spawn
				for _, p in parts do
					if p.name == "Spawn" then
						spawn = p
					end
				end
				for _, w in parts do
					if w.name == "Wall" then
						local overX = math.min(w.pos[1] + w.size[1] / 2, spawn.pos[1] + 3)
							- math.max(w.pos[1] - w.size[1] / 2, spawn.pos[1] - 3)
						local overZ = math.min(w.pos[3] + w.size[3] / 2, spawn.pos[3] + 3)
							- math.max(w.pos[3] - w.size[3] / 2, spawn.pos[3] - 3)
						check.truthy(overX <= 1e-6 or overZ <= 1e-6)
					end
				end
			end
		)

		test.case("the compiler: what cannot be built is said", function()
			local function wrong(more: any, text: string)
				local _, parts, errors = compile(spec(more))
				check.equal(#parts, 0)
				check.truthy(#errors >= 1)
				check.truthy(string.find(table.concat(errors, " | "), text, 1, true), table.concat(errors, " | "))
			end
			wrong({ rooms = 4 }, "cave.rooms")
			wrong({ fill = 0.7 }, "cave.fill")
			wrong({ mat = false }, "cave.mat is a palette entry's name")
			local bare = spec()
			bare.mat = nil
			local _, none, said = compile(bare)
			check.equal(#none, 0)
			check.truthy(string.find(table.concat(said, " | "), 'needs "mat"', 1, true), table.concat(said, " | "))
			-- a cave that closed up is not built, and says what to change
			local shut
			for seed = 1, 200 do
				if Cave.plan(spec({ seed = seed, fill = 0.5 })).share < Cave.LEAST then
					shut = seed
					break
				end
			end
			check.truthy(shut ~= nil)
			wrong({ seed = shut, fill = 0.5 }, "the cave closed up")
			wrong({ seed = shut, fill = 0.5 }, 'a lower "fill" (it is 0.5) or another seed')
			-- an unknown step is still told of the cave
			local _, _, issues = World.compile({ name = "T", palette = PALETTE, build = { { cavern = spec() } } })
			check.truthy(string.find(issues[1].message, "dungeon | cave |", 1, true))
		end)
	end)
end
