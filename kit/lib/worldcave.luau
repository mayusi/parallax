-- worldcave.luau (kit) — A CAVE GROWN BY A CELLULAR AUTOMATON (the owner's method list: "Cellular automata
-- generation"). The area is a grid of 4-stud cells. Each cell is rock or open by chance (`fill` = the share of
-- rock); then, a few turns, every cell looks at its eight neighbours and itself and becomes what most of them are
-- (rock when five or more of the nine are rock). Noise settles into chambers and winding passages.
--
-- What the automaton leaves is then made into a place a body can use, by rule:
--   1. open ground counts only where a body 8 studs wide can stand: in a square of 2 x 2 open cells (a doorway on
--      the rig's sheet is 8 studs);
--   2. such squares one cell apart are one slide of that body; the largest group of squares it can slide through
--      is the cave, and the cave's floor is what those squares cover (ground it would have to squeeze to is a
--      pocket, dropped);
--   3. floor that touches floor by a corner only is opened into a square that joins the group (a corner is no way
--      through, and two walls would stand in one place there).
-- So a body 8 studs wide gets from any place of the floor to any other, sliding along the grid - by construction,
-- and the compiler measures it again on the cells (Cave.wide).
--
-- The plan has the dungeon's shape (nx, nz, cell, kind[i][j] = 0 rock | 1 floor), so the dungeon's floor, wall and
-- walk functions build and check it (kit/lib/worlddungeon.luau: floors, walls, studs, reach).
-- Pure: no file reads, no game calls.
local Cave = {}

Cave.CELL = 4
Cave.DEFAULTS = { fill = 0.45, turns = 4, height = 12, thickness = 1 }
Cave.LEAST = 0.12 -- (the share of the area that must be floor: under it the cave has closed up)

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

local KEYS = {
	name = true,
	center = true,
	area = true,
	seed = true,
	fill = true,
	turns = true,
	height = true,
	thickness = true,
	mat = true,
	floor = true,
	roof = true,
	start = true,
	stream = true,
	landmark = true,
}

-- what is wrong with a cave step (nothing = it can be planned)
function Cave.problems(spec: any): { string }
	local out: { string } = {}
	if type(spec) ~= "table" then
		return { "a cave is { center, area, seed, mat, floor, ... }" }
	end
	for k in spec do
		if not KEYS[k] then
			table.insert(
				out,
				`cave.{tostring(k)} is not a word a cave knows (name, center, area, seed, fill, turns, height, thickness, mat, floor, roof, start, stream, landmark)`
			)
		end
	end
	if spec.name ~= nil and (type(spec.name) ~= "string" or spec.name == "") then
		table.insert(out, `cave.name is the cave's name (got {tostring(spec.name)})`)
	end
	local c = spec.center
	local function place(v: any): boolean
		return number(v) and math.abs(v) <= 1e6
	end
	if type(c) ~= "table" or #c ~= 3 or not (place(c[1]) and place(c[2]) and place(c[3])) then
		table.insert(out, "cave.center is [x, y, z] (the floor's top is at y), within a million studs of the middle")
	end
	local a = spec.area
	if
		type(a) ~= "table"
		or #a ~= 2
		or not (number(a[1]) and number(a[2]))
		or a[1] < 64
		or a[2] < 64
		or a[1] > 800
		or a[2] > 800
	then
		table.insert(out, "cave.area is [width, depth] in studs, 64 to 800 each way")
	end
	if spec.seed ~= nil and (not number(spec.seed) or spec.seed % 1 ~= 0 or spec.seed < 0 or spec.seed > 65535) then
		table.insert(out, `cave.seed is a whole number 0 to 65535 (got {tostring(spec.seed)})`)
	end
	if spec.fill ~= nil and (not number(spec.fill) or spec.fill < 0.3 or spec.fill > 0.5) then
		table.insert(
			out,
			`cave.fill is the share of rock the automaton starts from, 0.3 (wide halls) to 0.5 (narrow) (got {tostring(
				spec.fill
			)})`
		)
	end
	if spec.turns ~= nil and (not number(spec.turns) or spec.turns % 1 ~= 0 or spec.turns < 1 or spec.turns > 8) then
		table.insert(out, `cave.turns is how many times the rule is run, 1 to 8 (got {tostring(spec.turns)})`)
	end
	-- (12: the rig's sheet wants a ceiling that high, and a wall a body cannot jump onto)
	if spec.height ~= nil and (not number(spec.height) or spec.height < 12 or spec.height > 60) then
		table.insert(out, `cave.height is 12 to 60 studs (got {tostring(spec.height)})`)
	end
	if spec.thickness ~= nil and (not number(spec.thickness) or spec.thickness < 0.5 or spec.thickness > 2) then
		table.insert(out, `cave.thickness is 0.5 to 2 studs (got {tostring(spec.thickness)})`)
	end
	for _, word in { "mat", "floor", "roof" } do
		if spec[word] ~= nil and type(spec[word]) ~= "string" then
			table.insert(out, `cave.{word} is a palette entry's name (got {tostring(spec[word])})`)
		end
	end
	if spec.start ~= nil and type(spec.start) ~= "boolean" then
		table.insert(out, `cave.start is true or false (got {tostring(spec.start)})`)
	end
	return out
end

-- ONE TURN OF THE RULE on a grid of rock (true) and open (false): a cell is rock when five or more of the nine
-- cells round it (itself counted, off the grid = rock) are rock. -> a new grid
function Cave.turn(rock: { { boolean } }, nx: number, nz: number): { { boolean } }
	local out: { { boolean } } = table.create(nx)
	for i = 1, nx do
		local col = table.create(nz, false)
		for j = 1, nz do
			local n = 0
			for di = -1, 1 do
				for dj = -1, 1 do
					local a, b = i + di, j + dj
					if a < 1 or a > nx or b < 1 or b > nz or rock[a][b] then
						n += 1
					end
				end
			end
			col[j] = n >= 5
		end
		out[i] = col
	end
	return out
end

-- the grid as the automaton leaves it, before anything is mended (true = rock); its outermost ring is rock
function Cave.raw(spec: any): ({ { boolean } }, number, number)
	local d = Cave.DEFAULTS
	local rnd = lcg(spec.seed or 1)
	local nx, nz = math.floor(spec.area[1] / Cave.CELL), math.floor(spec.area[2] / Cave.CELL)
	local fill = spec.fill or d.fill
	local rock: { { boolean } } = table.create(nx)
	for i = 1, nx do
		local col = table.create(nz, false)
		for j = 1, nz do
			local chance = rnd() -- (drawn for every cell, the ring too: the same seed is the same cave)
			col[j] = i == 1 or i == nx or j == 1 or j == nz or chance < fill
		end
		rock[i] = col
	end
	for _ = 1, spec.turns or d.turns do
		-- (the outermost ring stays rock by the rule itself: a ring cell has three cells off the grid, itself and
		-- its two ring neighbours - six of nine)
		rock = Cave.turn(rock, nx, nz)
	end
	return rock, nx, nz
end

-- FLOOR THAT TOUCHES FLOOR BY A CORNER ONLY IS OPENED: the two rock cells of that square become floor, and one
-- more on each side of it, so that the new square is one slide from the square each corner came from (a corner's
-- cell stands in a square of floor on its far side; the square between that one and the new one lacks one cell) -
-- until there is none (an opening can make another, behind the place the sweep has reached). Changes `kind`
-- (0 rock | 1 floor) in place -> how many cells were opened
function Cave.open(kind: { { number } }, nx: number, nz: number): number
	local opened = 0
	local function fill(i: number, j: number)
		if i >= 2 and i <= nx - 1 and j >= 2 and j <= nz - 1 and kind[i][j] == 0 then
			kind[i][j] = 1
			opened += 1
		end
	end
	local again = true
	while again do
		again = false
		for i = 1, nx - 1 do
			for j = 1, nz - 1 do
				local a, b, c, d = kind[i][j], kind[i + 1][j], kind[i][j + 1], kind[i + 1][j + 1]
				if a == 1 and d == 1 and b == 0 and c == 0 then
					fill(i + 1, j)
					fill(i, j + 1)
					-- (one more on each side: the squares (i-1, j) and (i+1, j) then stand between the new square and
					-- the square each of the two corners came from)
					fill(i - 1, j + 1)
					fill(i + 2, j)
					again = true
				elseif b == 1 and c == 1 and a == 0 and d == 0 then
					fill(i, j)
					fill(i + 1, j + 1)
					fill(i + 2, j + 1)
					fill(i - 1, j)
					again = true
				end
			end
		end
	end
	return opened
end

-- THE SQUARES OF A FLOOR: sq[i][j] = true when the four cells (i, j) (i+1, j) (i, j+1) (i+1, j+1) are all floor -
-- a place where a body 8 studs wide stands. Two squares one cell apart (by a side) are one slide of that body.
-- -> sq, and piece[i][j] = which group of squares, joined by slides, the square is in (0 = no square), and the
-- groups' sizes in squares
function Cave.squares(kind: { { number } }, nx: number, nz: number): ({ { boolean } }, { { number } }, { number })
	local sq: { { boolean } } = table.create(nx)
	local piece: { { number } } = table.create(nx)
	for i = 1, nx do
		sq[i] = table.create(nz, false)
		piece[i] = table.create(nz, 0)
	end
	for i = 1, nx - 1 do
		for j = 1, nz - 1 do
			sq[i][j] = kind[i][j] ~= 0 and kind[i + 1][j] ~= 0 and kind[i][j + 1] ~= 0 and kind[i + 1][j + 1] ~= 0
		end
	end
	local sizes: { number } = {}
	for i = 1, nx - 1 do
		for j = 1, nz - 1 do
			if sq[i][j] and piece[i][j] == 0 then
				local id = #sizes + 1
				local n = 0
				local stack = { { i, j } }
				piece[i][j] = id
				while #stack > 0 do
					local at = table.remove(stack) :: { number }
					n += 1
					for _, d in { { 1, 0 }, { -1, 0 }, { 0, 1 }, { 0, -1 } } do
						local a, b = at[1] + d[1], at[2] + d[2]
						if a >= 1 and a <= nx and b >= 1 and b <= nz and sq[a][b] and piece[a][b] == 0 then
							piece[a][b] = id
							table.insert(stack, { a, b })
						end
					end
				end
				sizes[id] = n
			end
		end
	end
	return sq, piece, sizes
end

-- THE PLAN (call with a spec that has no problems). In CELLS, the grid's low corner at (0, 0):
--   nx, nz, cell; kind[i][j] = 0 rock | 1 floor; cells (floor cells), share (of the area);
--   closed, pockets, opened: how many cells each mending rule changed;
--   side = the side, in cells, of the largest square of floor (the widest chamber; 2 or more);
--   start = { u, v }: that square's middle, in cells from the grid's low corner (a cell's middle is at i - 0.5; an
--   even square's middle is a cell corner) - of equal squares the first in the grid's order;
--   far = { i, j } the floor cell the longest walk from the start, walk = that walk in cells;
--   rooms = { a cell of the start's square, as a one-cell room } (so the dungeon's walk can be run on it)
function Cave.plan(spec: any): any
	local rock, nx, nz = Cave.raw(spec)
	local open: { { number } } = table.create(nx)
	local was = 0
	for i = 1, nx do
		open[i] = table.create(nz, 0)
		for j = 1, nz do
			if not rock[i][j] then
				open[i][j] = 1
				was += 1
			end
		end
	end
	-- 1. and 2. the squares of open ground, in groups a body 8 studs wide can slide through; the largest group is
	-- the cave, and its floor is what its squares cover
	local sq, piece, sizes = Cave.squares(open, nx, nz)
	local best = 0
	for id, n in sizes do
		if best == 0 or n > sizes[best] then
			best = id
		end
	end
	local kind: { { number } } = table.create(nx)
	local inSquare: { { boolean } } = table.create(nx)
	for i = 1, nx do
		kind[i] = table.create(nz, 0)
		inSquare[i] = table.create(nz, false)
	end
	for i = 1, nx - 1 do
		for j = 1, nz - 1 do
			if sq[i][j] then
				inSquare[i][j], inSquare[i + 1][j], inSquare[i][j + 1], inSquare[i + 1][j + 1] = true, true, true, true
				if piece[i][j] == best then
					kind[i][j], kind[i + 1][j], kind[i][j + 1], kind[i + 1][j + 1] = 1, 1, 1, 1
				end
			end
		end
	end
	local closed, pockets = 0, 0
	for i = 1, nx do
		for j = 1, nz do
			if open[i][j] == 1 and kind[i][j] == 0 then
				if inSquare[i][j] then
					pockets += 1
				else
					closed += 1
				end
			end
		end
	end
	-- 3. floor that touches floor by a corner only is opened
	local opened = Cave.open(kind, nx, nz)
	-- the widest chamber: the largest square of floor (side[i][j] = the largest square whose high corner is the
	-- cell (i, j)); of equals the first in the grid's order
	local cells = 0
	local side = 0
	local start: { number }? = nil
	local corner: { number }? = nil
	local reach: { { number } } = table.create(nx)
	for i = 1, nx do
		reach[i] = table.create(nz, 0)
	end
	for i = 1, nx do
		for j = 1, nz do
			if kind[i][j] == 1 then
				cells += 1
				local n = 1
				if i > 1 and j > 1 then
					n = 1 + math.min(reach[i - 1][j], reach[i][j - 1], reach[i - 1][j - 1])
				end
				reach[i][j] = n
				if n > side then
					side = n
					start = { i - n / 2, j - n / 2 }
					corner = { i, j }
				end
			end
		end
	end
	-- the longest walk from the start (steps to the four neighbours), from the cell of its square nearest its middle
	local far: { number }? = nil
	local walk = 0
	local from: { number }? = nil
	if corner then
		from = { corner[1] - side // 2, corner[2] - side // 2 }
		far = from
		local steps: { [number]: number } = { [from[2] * (nx + 2) + from[1]] = 0 }
		local queue = { from }
		local head = 1
		while head <= #queue do
			local q = queue[head]
			head += 1
			local n = steps[q[2] * (nx + 2) + q[1]]
			if n > walk then
				walk = n
				far = q
			end
			for _, d in { { 1, 0 }, { -1, 0 }, { 0, 1 }, { 0, -1 } } do
				local a, b = q[1] + d[1], q[2] + d[2]
				if a >= 1 and a <= nx and b >= 1 and b <= nz and kind[a][b] == 1 and steps[b * (nx + 2) + a] == nil then
					steps[b * (nx + 2) + a] = n + 1
					table.insert(queue, { a, b })
				end
			end
		end
	end
	return {
		nx = nx,
		nz = nz,
		cell = Cave.CELL,
		kind = kind,
		cells = cells,
		share = cells / (nx * nz),
		was = was,
		closed = closed,
		pockets = pockets,
		opened = opened,
		side = side,
		start = start,
		from = from,
		far = far,
		walk = walk,
		rooms = if from then { { from[1], from[2], from[1], from[2] } } else {},
	}
end

-- HOW WIDE THE FLOOR IS, measured on the plan as it is (not on how it was made):
--   -> groups: how many groups of 8-stud squares there are that a body 8 studs wide cannot slide between (1 in a
--      plan that can be built: such a body gets from any square of the floor to any other);
--      thin: how many floor cells lie in no 8-stud square of floor (0 in a plan that can be built)
function Cave.wide(plan: any): (number, number)
	local sq, _, sizes = Cave.squares(plan.kind, plan.nx, plan.nz)
	local covered: { [number]: boolean } = {}
	for i = 1, plan.nx - 1 do
		for j = 1, plan.nz - 1 do
			if sq[i][j] then
				for _, d in { { 0, 0 }, { 1, 0 }, { 0, 1 }, { 1, 1 } } do
					covered[(j + d[2]) * (plan.nx + 2) + i + d[1]] = true
				end
			end
		end
	end
	local thin = 0
	for i = 1, plan.nx do
		for j = 1, plan.nz do
			if plan.kind[i][j] ~= 0 and not covered[j * (plan.nx + 2) + i] then
				thin += 1
			end
		end
	end
	return #sizes, thin
end

-- floor that touches floor by a corner only (0 in a plan that can be built)
function Cave.pinches(plan: any): number
	local n = 0
	for i = 1, plan.nx - 1 do
		for j = 1, plan.nz - 1 do
			local a, b, c, d = plan.kind[i][j], plan.kind[i + 1][j], plan.kind[i][j + 1], plan.kind[i + 1][j + 1]
			if (a ~= 0 and d ~= 0 and b == 0 and c == 0) or (b ~= 0 and c ~= 0 and a == 0 and d == 0) then
				n += 1
			end
		end
	end
	return n
end

return Cave
