-- worldfacade.spec.luau (kit) — the facade grammar (kit/lib/worldfacade.luau): a wall split into its openings and
-- the runs between, each a stretched module; what the compiler makes of a building and of a town that wears one.
local frk = require("../frk")
local test, check = frk.test, frk.check

local Facade = require("../../lib/worldfacade")
local Run = require("../../lib/run")
local Town = require("../../lib/worldtown")
local World = require("../../lib/world")
local WorldCmd = require("../../cmd/world")
local fs = require("@lune/fs")
local serde = require("@lune/serde")

local PALETTE = {
	cobble = { material = "Cobblestone", color = { 84, 82, 80 } },
	pave = { material = "Slate", color = { 98, 96, 94 } },
	plaster = { material = "Concrete", color = { 150, 140, 124 } },
	slate = { material = "Slate", color = { 58, 60, 68 } },
}
local MATS = { street = "cobble", block = "pave", wall = "plaster", roof = "slate" }

local function near(a: number, b: number, eps: number?): boolean
	return math.abs(a - b) <= (eps or 1e-6)
end

-- a module as kit world meshes files it: its recipe's box, its origin at the foot of its middle on the wall's line
local function registry(recipes: { any }): { [string]: any }
	local reg = {}
	for _, r in recipes do
		reg[r.name] = {
			kind = r.kind,
			module = r.module,
			floorHeight = r.floorHeight,
			gap = r.gap,
			size = r.size,
			min = { -r.size[1] / 2, 0, -r.size[3] / 2 },
		}
	end
	return reg
end

local LOOK = {
	prefix = "fx",
	floorHeights = { 14 },
	thickness = 1.2,
	door = { width = 5, height = 8.5 },
	window = { width = 4, height = 10.5, sill = 3.5 },
}

local function house(more: any?): any
	local b: any = {
		name = "House",
		center = { 0, 0, 0 },
		size = { 23, 24 },
		floors = 2,
		floorHeight = 14,
		thickness = 1,
		mat = "plaster",
		roof = "gable",
		roofMat = "slate",
		door = { side = "S", width = 5, height = 8.5 },
		windows = { every = 10, width = 4, height = 7, sill = 3.5, sides = { "S", "E" } },
		facade = "fx",
		seed = 2,
	}
	for k, v in more or {} do
		b[k] = v
	end
	return b
end

local function compile(buildings: { any }, reg: any): ({ any }, { any }, any)
	local build = {}
	for _, b in buildings do
		table.insert(build, { building = b })
	end
	local _, parts, issues, extras = World.compile(
		{ name = "T", palette = PALETTE, scale = "r6", build = build },
		{ meshes = reg }
	)
	local errors = {}
	for _, i in issues do
		if i.severity == "error" then
			table.insert(errors, i)
		end
	end
	return parts, errors, extras
end

return function()
	test.suite("Facade grammar: one wall, split", function()
		test.case(
			"the pieces cover the wall from end to end, each gap its own module, the runs whole panels",
			function()
				local walls = 0
				for _, len in { 8, 15, 19, 23, 24, 31.5, 60 } do
					for _, every in { 6, 10, 13 } do
						local n = math.floor((len - 4) / every)
						local gaps = {}
						for k = 1, n do
							-- (given out of order: the grammar sorts them)
							table.insert(
								gaps,
								1,
								{ at = (k - 0.5) * len / n, width = 4, sill = if k == 2 then 0 else 3.5 }
							)
						end
						local pieces = Facade.wall(len, gaps, { window = "windowb" })
						walls += 1
						local cursor, openings = 0, 0
						for _, p in pieces do
							check.truthy(near(p.at - p.width / 2, cursor, 1e-9)) -- (no gap and no overlap)
							cursor = p.at + p.width / 2
							if p.kind ~= "wall" then
								openings += 1
								check.truthy(near(p.width, 4))
								local own = nil
								for _, g in gaps do
									own = own or (if near(g.at, p.at) then g else nil)
								end
								check.truthy(own ~= nil)
								check.equal(p.kind, if own.sill == 0 then "door" else "windowb")
							else
								-- a panel is the 4-stud module stretched: never past half as wide again, and - where the
								-- run is 3 studs or more - never under three quarters
								check.truthy(p.width <= 6 + 1e-9)
							end
						end
						check.truthy(near(cursor, len, 1e-9))
						check.equal(openings, n)
					end
				end
				check.equal(walls, 21)
				-- a run of 11.5 studs is three panels of 3.83, one of 5.5 is one panel, one of 6 is two
				local three = Facade.wall(11.5, {})
				check.equal(#three, 3)
				check.truthy(near(three[1].width, 11.5 / 3))
				check.equal(#Facade.wall(5.5, {}), 1)
				check.equal(#Facade.wall(6, {}), 2)
				-- no gaps: all wall; a wall that is all gap: one module
				check.equal(Facade.wall(4, { { at = 2, width = 4, sill = 3 } })[1].kind, "window")
				check.equal(#Facade.wall(4, { { at = 2, width = 4, sill = 3 } }), 1)
			end
		)

		test.case("which gap is the oriel, and a gap the wall cannot hold is left out", function()
			local gaps = {
				{ at = 4, width = 4, sill = 3.5 },
				{ at = 12, width = 4, sill = 3.5 },
				{ at = 20, width = 4, sill = 3.5 },
			}
			local kinds = {}
			for _, p in Facade.wall(24, gaps, { oriel = 2 }) do
				if p.kind ~= "wall" then
					table.insert(kinds, p.kind)
				end
			end
			check.equal(table.concat(kinds, " "), "window oriel window")
			-- (a door is never an oriel, whatever the index says)
			check.equal(Facade.wall(8, { { at = 4, width = 4, sill = 0 } }, { oriel = 1 })[2].kind, "door")
			-- a gap with no width, a negative one, one with no number for its place: no opening, the wall whole
			for _, bad in
				{
					{ at = 5, width = 0, sill = 3 },
					{ at = 5, width = -2, sill = 3 },
					{ at = 0 / 0, width = 4, sill = 3 },
				}
			do
				local whole = Facade.wall(10, { bad })
				local at = 0
				for _, p in whole do
					check.equal(p.kind, "wall")
					check.truthy(p.width > 0 and near(p.at - p.width / 2, at, 1e-9))
					at = p.at + p.width / 2
				end
				check.truthy(near(at, 10, 1e-9))
			end
			-- a gap past the wall's end, one over the gap before: left out, the wall still covered
			local odd = Facade.wall(
				10,
				{ { at = 3, width = 4, sill = 3 }, { at = 4, width = 4, sill = 3 }, { at = 9.5, width = 4, sill = 3 } }
			)
			local cursor = 0
			for _, p in odd do
				check.truthy(near(p.at - p.width / 2, cursor, 1e-9))
				cursor = p.at + p.width / 2
			end
			check.truthy(near(cursor, 10, 1e-9))
		end)

		test.case("a band along a wall: whole 8-stud modules stretched to fit", function()
			for _, len in { 3, 8, 15, 23, 40 } do
				local pieces = Facade.band(len)
				local cursor = 0
				for _, p in pieces do
					check.truthy(near(p.at - p.width / 2, cursor, 1e-9))
					cursor = p.at + p.width / 2
				end
				check.truthy(near(cursor, len, 1e-9))
				check.equal(#pieces, math.max(1, math.floor(len / 8 + 0.5)))
			end
		end)

		test.case("a house's seed picks its window and its oriel: the same for one seed, mixed over a town", function()
			local b, oriels, tall = 0, 0, 0
			for seed = 1, 600 do
				local win, oriel = Facade.pick(seed, 3)
				local again, oriel2 = Facade.pick(seed, 3)
				check.equal(win, again)
				check.equal(oriel, oriel2)
				check.truthy(win == "window" or win == "windowb")
				b += if win == "windowb" then 1 else 0
				oriels += if oriel then 1 else 0
				local _, low = Facade.pick(seed, 1)
				tall += if low then 1 else 0
			end
			check.truthy(b > 250 and b < 350) -- (about half)
			check.truthy(oriels > 160 and oriels < 240) -- (about one house in three)
			check.equal(tall, 0) -- (a house of one storey has no storey to hang an oriel on)
			-- houses along a street have seeds a fixed step apart: their windows must not alternate house by house,
			-- nor the pattern come round every few houses (read straight off the seed it came round every sixth)
			for _, step in { 1, 2, 131, 100003 } do
				local seq = {}
				for k = 1, 240 do
					local win, oriel = Facade.pick(7 + k * step, 3)
					seq[k] = (if win == "window" then "w" else "b") .. (if oriel then "O" else "-")
				end
				local same = 0
				for k = 2, 240 do
					same += if string.sub(seq[k], 1, 1) == string.sub(seq[k - 1], 1, 1) then 1 else 0
				end
				check.truthy(same > 85 and same < 155) -- (a neighbour wears the same window about half the time)
				for period = 1, 24 do
					local repeats = 0
					for k = period + 1, 240 do
						repeats += if seq[k] == seq[k - period] then 1 else 0
					end
					check.truthy(repeats < (240 - period) * 0.5) -- (no period: chance is about a third, a true repeat all)
				end
			end
			-- a chimney on about half the houses, not tied to the window
			local chimneys, both = 0, 0
			for seed = 1, 600 do
				local c = Facade.chimney(seed)
				check.equal(c, Facade.chimney(seed))
				chimneys += if c then 1 else 0
				both += if c and Facade.pick(seed, 3) == "window" then 1 else 0
			end
			check.truthy(chimneys > 250 and chimneys < 350)
			check.truthy(both > 100 and both < 200)
		end)
	end)

	test.suite("Facade grammar: the kit and the fit", function()
		test.case("five modules a storey height and three for the town, cut for the town's own openings", function()
			local one = Facade.kit(LOOK)
			check.equal(#one, 8)
			local two = Facade.kit({
				prefix = "fx",
				floorHeights = { 15, 12.5 },
				thickness = 1.2,
				door = LOOK.door,
				window = LOOK.window,
			})
			check.equal(#two, 13)
			local names = {}
			for _, r in two do
				check.equal(names[r.name], nil)
				names[r.name] = r
				check.equal(r.kind, "gothic_module")
			end
			check.truthy(
				names.fx_wall_15 and names["fx_wall_12.5"] and names.fx_oriel_15 and names.fx_roof and names.fx_band
			)
			check.equal(names.fx_door_15.gap.width, 5)
			check.equal(names.fx_door_15.gap.sill, 0)
			check.equal(names.fx_windowb_15.gap.height, 10.5)
			check.equal(names.fx_window_15.size[2], 15)
			check.equal(names["fx_window_12.5"].size[2], 12.5)
			check.equal(names.fx_wall_15.size[1], 4)
			check.equal(Facade.name("gc", "roof", 14), "gc_roof")
			-- two storey heights a thirtieth apart are two names (to a tenth they were one); the same height twice is one
			check.truthy(Facade.name("gc", "wall", 13.3) ~= Facade.name("gc", "wall", 13.34))
			check.equal(Facade.name("gc", "wall", 13.34), "gc_wall_13.34")
			check.equal(Facade.name("gc", "wall", 12.5), "gc_wall_12.5")
			local near2 = Facade.kit({
				prefix = "fx",
				floorHeights = { 13.3, 13.34, 13.3 },
				thickness = 1.2,
				door = LOOK.door,
				window = LOOK.window,
			})
			check.equal(#near2, 13)
			local seen = {}
			for _, r in near2 do
				check.equal(seen[r.name], nil)
				seen[r.name] = true
			end
			check.equal(#Facade.kit({
				prefix = "fx",
				floorHeights = { 13, 14, 15 },
				thickness = 1.2,
				door = LOOK.door,
				window = LOOK.window,
			}), 18)
			check.equal(Facade.name("gc", "door", 14), "gc_door_14")
		end)

		test.case("why a module cannot fill a place", function()
			local reg = registry(Facade.kit(LOOK))
			local gap = { width = 4, height = 10.5, sill = 3.5 }
			check.equal(
				Facade.problem(reg.fx_window_14, "fx_window_14", { kind = "window", floorHeight = 14, gap = gap }),
				nil
			)
			local function says(got: string?, part: string)
				check.truthy(got ~= nil and string.find(got :: string, part, 1, true) ~= nil)
			end
			says(Facade.problem(nil, "fx_window_14", { kind = "window" }), 'no world mesh "fx_window_14"')
			-- an entry with no box or no origin is said, not crashed on
			local noMin = table.clone(reg.fx_wall_14)
			noMin.min = nil
			says(Facade.problem(noMin, "fx_wall_14", { kind = "wall", floorHeight = 14 }), "has no min in the registry")
			local noSize = table.clone(reg.fx_wall_14)
			noSize.size = { 4, 14 }
			says(
				Facade.problem(noSize, "fx_wall_14", { kind = "wall", floorHeight = 14 }),
				"has no size in the registry"
			)
			says(Facade.problem(reg.fx_wall_14, "fx_wall_14", { kind = "window" }), 'is no "window" module')
			says(
				Facade.problem({ kind = "gothic_house", size = { 1, 1, 1 } }, "h", { kind = "wall" }),
				"it is a gothic_house"
			)
			says(
				Facade.problem(reg.fx_window_14, "fx_window_14", { kind = "window", floorHeight = 12, gap = gap }),
				"made for a storey of 14, the house's is 12"
			)
			for _, k in { "width", "height", "sill" } do
				local other = table.clone(gap)
				other[k] += 0.5
				says(
					Facade.problem(reg.fx_window_14, "fx_window_14", { kind = "window", floorHeight = 14, gap = other }),
					`opening has {k}`
				)
				-- (a twentieth of a stud is the same opening)
				other[k] = gap[k] + 0.04
				check.equal(
					Facade.problem(reg.fx_window_14, "fx_window_14", { kind = "window", floorHeight = 14, gap = other }),
					nil
				)
			end
			-- the roof module (20 wide, 24 along its ridge): grown with the house's front, tiled along its ridge
			check.equal(Facade.problem(reg.fx_roof, "fx_roof", { kind = "roof", front = 25, depth = 26 }), nil)
			check.equal(Facade.problem(reg.fx_roof, "fx_roof", { kind = "roof", front = 11, depth = 24 }), nil)
			check.equal(Facade.problem(reg.fx_roof, "fx_roof", { kind = "roof", front = 17, depth = 90 }), nil)
			check.equal(Facade.problem(reg.fx_roof, "fx_roof", { kind = "roof", front = 43, depth = 27 }), nil) -- (turned)
			says(
				Facade.problem(reg.fx_roof, "fx_roof", { kind = "roof", front = 9, depth = 12 }),
				"0.45 times its size"
			)
			says(
				Facade.problem(reg.fx_roof, "fx_roof", { kind = "roof", front = 45, depth = 44 }),
				"2.25 times its size"
			)
			-- a house wider than deep: the street gable would be squeezed along its ridge, so the ridge runs along the
			-- front instead (turned) - and over every shape a house can have, no roof module is skewed past 0.6..1.6
			-- and the modules lie end to end along the ridge
			check.equal(Facade.problem(reg.fx_roof, "fx_roof", { kind = "roof", front = 20, depth = 14 }), nil)
			check.equal(Facade.roof(20, 14, { 20, 14, 24 }).turned, true)
			check.equal(Facade.roof(20, 24, { 20, 14, 24 }).turned, false)
			check.equal(Facade.roof(17, 90, { 20, 14, 24 }).turned, false)
			local turnedSeen = 0
			for front = 8, 60 do
				for depth = 8, 90, 2 do
					local r = Facade.roof(front, depth, { 20, 14, 24 })
					local ridge = if r.turned then front else depth
					local gable = if r.turned then depth else front
					turnedSeen += if r.turned then 1 else 0
					check.truthy(near(r.scale, gable / 20))
					local cursor = -ridge / 2
					for _, tile in r.tiles do
						local skew = tile.stretch / r.scale
						check.truthy(skew >= 0.6 and skew <= 1.6)
						check.truthy(near(tile.at - tile.stretch * 24 / 2, cursor, 1e-9))
						cursor = tile.at + tile.stretch * 24 / 2
					end
					check.truthy(near(cursor, ridge / 2, 1e-9))
					check.truthy(not r.turned or front > depth) -- (only a house wider than deep is ever turned)
				end
			end
			check.truthy(turnedSeen > 100)
			says(
				Facade.problem(
					{ kind = "gothic_module", module = "roof" },
					"r",
					{ kind = "roof", front = 20, depth = 20 }
				),
				"no size"
			)
		end)
	end)

	test.suite("Facade grammar: a building made of modules", function()
		local REG = registry(Facade.kit(LOOK))

		test.case("the walls it stands on are the plain building's own, unseen; the modules are seen only", function()
			local plain, plainErrors = compile({ house({ facade = false }) }, REG)
			local parts, errors = compile({ house() }, REG)
			check.equal(#plainErrors, 0)
			check.equal(#errors, 0)
			local function solids(list: { any }): { string }
				local out = {}
				for _, p in list do
					if
						p.name == "Wall"
						or p.name == "Sill"
						or p.name == "Lintel"
						or p.name == "Slab"
						or p.name == "Floor"
					then
						table.insert(
							out,
							string.format(
								"%s %.3f %.3f %.3f %.3f %.3f %.3f %s",
								p.name,
								p.pos[1],
								p.pos[2],
								p.pos[3],
								p.size[1],
								p.size[2],
								p.size[3],
								tostring(p.collide)
							)
						)
					end
				end
				table.sort(out)
				return out
			end
			local a, b = solids(plain), solids(parts)
			check.truthy(#a > 20)
			check.equal(table.concat(a, "\n"), table.concat(b, "\n"))
			local modules = 0
			for _, p in parts do
				if
					p.name == "Wall"
					or p.name == "Sill"
					or p.name == "Lintel"
					or p.name == "RoofN"
					or p.name == "RoofS"
				then
					check.equal(p.transparency, 1)
				elseif p.mesh then
					modules += 1
					check.equal(p.collide, false)
					check.equal(p.transparency, 1) -- (a placeholder: the runtime swaps the mesh in)
					check.equal(p.attributes.Collide, false)
					check.truthy(REG[p.mesh] ~= nil and REG[p.mesh].module == p.module)
				end
			end
			check.truthy(modules > 30)
			for _, p in plain do
				check.truthy(p.mesh == nil)
				if p.name == "Wall" then
					check.equal(p.transparency, 0)
				end
			end
		end)

		test.case("every window and the door stand where the wall is cut; every wall is covered once", function()
			for _, side in { "S", "E", "N", "W" } do
				for _, size in { { 23, 24 }, { 15, 19 }, { 31, 24 } } do
					local parts, errors = compile({
						house({
							size = size,
							door = { side = side, width = 5, height = 8.5 },
							windows = { every = 10, width = 4, height = 7, sill = 3.5 },
						}),
					}, REG)
					check.equal(#errors, 0)
					-- a Sill is what the compiler leaves under a window: one window module on each, the gap's width
					local sills, windows, doors, lengths = {}, 0, 0, {}
					for _, p in parts do
						if p.name == "Sill" then
							table.insert(sills, p)
						end
					end
					for _, p in parts do
						if p.mesh and (p.module == "window" or p.module == "windowb" or p.module == "oriel") then
							windows += 1
							local on = false
							for _, sl in sills do
								on = on
									or (
										near(sl.pos[1], p.pos[1], 1e-6)
										and near(sl.pos[3], p.pos[3], 1e-6)
										and near(sl.pos[2] - sl.size[2] / 2, p.pos[2] - p.size[2] / 2, 1e-6)
									)
							end
							check.truthy(on)
							check.truthy(near(p.size[1], 4) and near(p.size[2], 14))
						elseif p.mesh and p.module == "door" then
							doors += 1
							-- (over a doorway the compiler leaves a Lintel from the door's height up, and no Sill under it)
							local claimed = false
							for _, q in parts do
								claimed = claimed
									or (
										q.name == "Lintel"
										and near(q.pos[1], p.pos[1], 1e-6)
										and near(q.pos[3], p.pos[3], 1e-6)
										and near(q.pos[2] - q.size[2] / 2, 8.5, 1e-6)
									)
							end
							check.truthy(claimed)
							check.truthy(near(p.size[1], 5))
						end
						if
							p.mesh
							and (
								p.module == "wall"
								or p.module == "window"
								or p.module == "windowb"
								or p.module == "oriel"
								or p.module == "door"
							)
						then
							-- which wall and storey: by its facing (its rot) and its foot
							local key = string.format(
								"%.0f %.0f %.1f",
								p.rot[1][1] * 10,
								p.rot[1][3] * 10,
								p.pos[2] - p.size[2] / 2
							)
							lengths[key] = (lengths[key] or 0) + p.size[1]
						end
					end
					check.equal(windows, #sills)
					check.equal(doors, 1)
					local walls = 0
					for key, total in lengths do
						walls += 1
						local alongX = string.sub(key, 1, 2) ~= "0 " and string.sub(key, 1, 2) ~= "-0"
						check.truthy(near(total, if alongX then size[1] else size[2], 1e-6))
					end
					check.equal(walls, 8) -- (four walls, two storeys)
				end
			end
		end)

		test.case("a module modelled at another size than its place is stretched to the place", function()
			-- a wall panel modelled 5 wide and 13.5 tall, a window 4 x 13.5 (their storey still 14): each one placed
			-- fills its piece of the wall and its storey, whatever its own box
			local odd = table.clone(REG)
			for _, name in { "fx_wall_14", "fx_window_14", "fx_windowb_14", "fx_door_14", "fx_oriel_14" } do
				odd[name] = table.clone(REG[name])
				local own = REG[name].size
				odd[name].size = { own[1] + 1, 13.5, own[3] }
				odd[name].min = { -(own[1] + 1) / 2, 0, -own[3] / 2 }
			end
			local parts, errors = compile({ house() }, odd)
			local same = compile({ house() }, REG)
			check.equal(#errors, 0)
			local function boxes(list: { any }): string
				local out = {}
				for _, p in list do
					if p.mesh then
						table.insert(
							out,
							string.format(
								"%s %.4f %.4f %.4f | %.4f %.4f %.4f",
								p.mesh,
								p.pos[1],
								p.pos[2],
								p.pos[3],
								p.size[1],
								p.size[2],
								p.size[3]
							)
						)
					end
				end
				table.sort(out)
				return table.concat(out, "\n")
			end
			check.equal(boxes(parts), boxes(same))
		end)

		test.case("bands between storeys, one roof turned to the door, a chimney on some", function()
			local chimneys = 0
			for seed = 1, 40 do
				for _, side in { "S", "E", "N", "W" } do
					local parts, errors =
						compile({ house({ seed = seed, door = { side = side, width = 5, height = 8.5 } }) }, REG)
					check.equal(#errors, 0)
					local roofs, bands, bandLen = {}, 0, 0
					for _, p in parts do
						if p.module == "roof" then
							table.insert(roofs, p)
						elseif p.module == "band" then
							bands += 1
							bandLen += p.size[1]
							check.truthy(near(p.pos[2] - p.size[2] / 2, 14)) -- (at the upper storey's foot)
						elseif p.module == "chimney" then
							chimneys += 1
						end
					end
					check.equal(#roofs, 1)
					check.truthy(near(bandLen, 2 * (23 + 24), 1e-6))
					check.truthy(bands >= 8)
					-- the roof covers the house and its walls: 25 x 26 seen from above, whichever way it faces, on the top
					local r = roofs[1]
					local alongX = side == "S" or side == "N"
					local wx = math.abs(r.rot[1][1]) * r.size[1] + math.abs(r.rot[1][3]) * r.size[3]
					local wz = math.abs(r.rot[3][1]) * r.size[1] + math.abs(r.rot[3][3]) * r.size[3]
					check.truthy(near(wx, 25, 1e-6) and near(wz, 26, 1e-6))
					check.truthy(near(r.size[1], if alongX then 25 else 26, 1e-6))
					check.truthy(near(r.pos[2] - r.size[2] / 2, 28, 1e-6))
					check.truthy(near(r.pos[1], 0, 1e-6) and near(r.pos[3], 0, 1e-6))
					-- its height stretched with its front: the module's own pitch
					check.truthy(near(r.size[2] / r.size[1], 14 / 20, 1e-6))
				end
			end
			check.truthy(chimneys > 40 and chimneys < 120) -- (about half of 160)
			-- THE ROOF BY RULE (Facade.roof), measured on the modules as placed: together they cover the house and
			-- its walls exactly, whatever its shape
			for _, shape in { { 23, 24, 1 }, { 15, 45, 2 }, { 15, 80, 4 }, { 41, 25, 1 }, { 60, 20, 2 } } do
				for _, side in { "S", "E", "N", "W" } do
					local alongX = side == "S" or side == "N"
					local size = if alongX then { shape[1], shape[2] } else { shape[2], shape[1] }
					local parts, errors =
						compile({ house({ size = size, door = { side = side, width = 5, height = 8.5 } }) }, REG)
					check.equal(#errors, 0)
					local x0, x1, z0, z1, n, area = math.huge, -math.huge, math.huge, -math.huge, 0, 0
					for _, p in parts do
						if p.module == "roof" then
							n += 1
							local wx = math.abs(p.rot[1][1]) * p.size[1] + math.abs(p.rot[1][3]) * p.size[3]
							local wz = math.abs(p.rot[3][1]) * p.size[1] + math.abs(p.rot[3][3]) * p.size[3]
							x0, x1 = math.min(x0, p.pos[1] - wx / 2), math.max(x1, p.pos[1] + wx / 2)
							z0, z1 = math.min(z0, p.pos[3] - wz / 2), math.max(z1, p.pos[3] + wz / 2)
							area += wx * wz
							-- no module's slates smeared: its ridge stretch within 0.6..1.6 of its front's
							local skew = (p.size[3] / 24) / (p.size[1] / 20)
							check.truthy(skew >= 0.6 and skew <= 1.6)
							check.truthy(near(p.size[2] / p.size[1], 14 / 20, 1e-6))
						end
					end
					check.equal(n, shape[3])
					check.truthy(near(x1 - x0, size[1] + 2, 1e-6) and near(z1 - z0, size[2] + 2, 1e-6))
					check.truthy(near(x0 + x1, 0, 1e-6) and near(z0 + z1, 0, 1e-6))
					check.truthy(near(area, (size[1] + 2) * (size[2] + 2), 1e-6)) -- (side by side: none over another)
				end
			end
			-- one storey: no band, no oriel
			local low = compile({ house({ floors = 1 }) }, REG)
			for _, p in low do
				check.truthy(p.module ~= "band" and p.module ~= "oriel")
			end
		end)

		test.case("houses of one size differ by their seed: the second window, an oriel over the door", function()
			local looks = {}
			local oriels = 0
			for seed = 1, 40 do
				local parts = compile({ house({ seed = seed, floors = 3, size = { 35, 24 } }) }, REG)
				local counts = {}
				for _, p in parts do
					if p.module then
						counts[p.module] = (counts[p.module] or 0) + 1
					end
				end
				looks[`{counts.window or 0}/{counts.windowb or 0}/{counts.oriel or 0}`] = true
				check.truthy((counts.oriel or 0) <= 1)
				check.truthy((counts.window or 0) == 0 or (counts.windowb or 0) == 0) -- (one window kind a house)
				oriels += counts.oriel or 0
				if counts.oriel then
					-- the oriel: over the door, on the first upper storey
					for _, p in parts do
						if p.module == "oriel" then
							check.truthy(near(p.pos[2] - p.size[2] / 2, 14))
							check.truthy(p.pos[3] > 11) -- (the south wall: the door's)
							-- ... straight over the door (the middle of three bays), not over a window beside it
							local over = false
							for _, q in parts do
								over = over or (q.module == "door" and near(q.pos[1], p.pos[1], 1e-6))
							end
							check.truthy(over)
						end
					end
				end
			end
			local n = 0
			for _ in looks do
				n += 1
			end
			check.equal(n, 4) -- (two windows x with / without an oriel)
			check.truthy(oriels >= 6 and oriels <= 22) -- (about one in three of 40)
		end)

		test.case("the roof you bump into is the roof you see: one ridge, one height, one footprint", function()
			for _, shape in { { 23, 24 }, { 15, 45 }, { 41, 25 }, { 17, 19 }, { 60, 20 } } do
				for _, side in { "S", "E", "N", "W" } do
					local alongX = side == "S" or side == "N"
					local size = if alongX then { shape[1], shape[2] } else { shape[2], shape[1] }
					local parts =
						compile({ house({ size = size, door = { side = side, width = 5, height = 8.5 } }) }, REG)
					local function box(want: (any) -> boolean): (number, number, number, number, number, number)
						local x0, x1, z0, z1, y1, n = math.huge, -math.huge, math.huge, -math.huge, -math.huge, 0
						for _, p in parts do
							if want(p) then
								n += 1
								local wx = math.abs(p.rot[1][1]) * p.size[1] + math.abs(p.rot[1][3]) * p.size[3]
								local wz = math.abs(p.rot[3][1]) * p.size[1] + math.abs(p.rot[3][3]) * p.size[3]
								x0, x1 = math.min(x0, p.pos[1] - wx / 2), math.max(x1, p.pos[1] + wx / 2)
								z0, z1 = math.min(z0, p.pos[3] - wz / 2), math.max(z1, p.pos[3] + wz / 2)
								y1 = math.max(y1, p.pos[2] + p.size[2] / 2)
							end
						end
						return x0, x1, z0, z1, y1, n
					end
					local sx0, sx1, sz0, sz1, sy, seen = box(function(p)
						return p.module == "roof"
					end)
					local hx0, hx1, hz0, hz1, hy, hidden = box(function(p)
						return p.name == "RoofN" or p.name == "RoofS"
					end)
					check.equal(hidden, 2)
					check.truthy(seen >= 1)
					check.truthy(
						near(sx0, hx0, 1e-6) and near(sx1, hx1, 1e-6) and near(sz0, hz0, 1e-6) and near(sz1, hz1, 1e-6)
					)
					check.truthy(near(sy, hy, 1e-6)) -- (the ridge's height)
					-- ... and the ridge runs the same way: the seen module's own +Z (along its ridge) against the two
					-- hidden wedges, which lie either side of the ridge
					local ridgeX = false
					for _, p in parts do
						if p.module == "roof" then
							ridgeX = math.abs(p.rot[1][3]) > 0.5
						end
					end
					for _, p in parts do
						if p.name == "RoofN" or p.name == "RoofS" then
							check.equal(p.transparency, 1)
							-- (a wedge either side of a ridge along X stands off the middle in Z, and the other way round)
							check.truthy(
								if ridgeX
									then near(p.pos[1], 0, 1e-6) and math.abs(p.pos[3]) > 1
									else near(p.pos[3], 0, 1e-6) and math.abs(p.pos[1]) > 1
							)
						end
					end
				end
			end
		end)

		test.case("a chimney stands out of the roof's slope, on the house; a flat roof stays the seen slab", function()
			local seenChimneys = 0
			for seed = 1, 30 do
				for _, shape in { { 23, 24 }, { 15, 45 }, { 41, 25 }, { 31, 24 } } do
					for _, side in { "S", "E" } do
						local alongX = side == "S"
						local size = if alongX then { shape[1], shape[2] } else { shape[2], shape[1] }
						local parts = compile(
							{ house({ seed = seed, size = size, door = { side = side, width = 5, height = 8.5 } }) },
							REG
						)
						local roofTop, gable, ridgeX = 0, 0, false
						for _, p in parts do
							if p.module == "roof" then
								roofTop = p.pos[2] + p.size[2] / 2
								gable = p.size[1]
								ridgeX = math.abs(p.rot[1][3]) > 0.5
							end
						end
						for _, p in parts do
							if p.module == "chimney" then
								seenChimneys += 1
								-- on the house: inside its walls' footprint
								check.truthy(math.abs(p.pos[1]) < size[1] / 2 and math.abs(p.pos[3]) < size[2] / 2)
								-- the roof's own surface under the chimney's middle: from the eaves (28) up to the ridge
								local off = if ridgeX then math.abs(p.pos[3]) else math.abs(p.pos[1])
								local surface = 28 + (roofTop - 28) * (1 - off / (gable / 2))
								check.truthy(off > 1) -- (off the ridge)
								local top, foot = p.pos[2] + p.size[2] / 2, p.pos[2] - p.size[2] / 2
								check.truthy(top - surface >= 3) -- (at least 3 studs of it stand out of the slates)
								check.truthy(foot < surface) -- (and its foot is in the roof, not in the air)
								-- ... on its DOWNHILL side too: the roof falls 1.4 a stud (the module's pitch) across the
								-- stack's half width; set by its middle alone the lower face hung 0.9 studs over the slates
								check.truthy(foot <= surface - 1.4 * p.size[1] / 2 - 0.4)
							end
						end
					end
				end
			end
			check.truthy(seenChimneys > 60)
			-- a flat roof: no roof module, the slab seen (it was hidden with nothing over it: a house open to the sky)
			local flat, errors = compile({ house({ roof = "flat" }) }, REG)
			check.equal(#errors, 0)
			local slabs = 0
			for _, p in flat do
				check.truthy(p.module ~= "roof" and p.module ~= "chimney")
				if p.name == "Roof" then
					slabs += 1
					check.equal(p.transparency, 0)
				end
			end
			check.equal(slabs, 1)
		end)

		test.case("a mesh larger than its recipe's box is stretched by the BOX, not by its own bounds", function()
			-- as kit world meshes files a real window: its box 4 x 14 x 1.2, its mesh 4 x 14 x 1.38 (a hood mould
			-- 0.18 proud) - and a real oriel 4.3 wide (its little roof overhangs). Stretched by their own bounds
			-- the oriel would come out 7% narrow; by the box each keeps its size and only its place is filled
			local real = table.clone(REG)
			real.fx_window_14 = table.clone(REG.fx_window_14)
			real.fx_window_14.box = { 4, 14, 1.2 }
			real.fx_window_14.size = { 4, 14, 1.38 }
			real.fx_window_14.min = { -2, 0, -0.6 }
			real.fx_windowb_14 = table.clone(real.fx_window_14)
			real.fx_windowb_14.module = "windowb"
			real.fx_oriel_14 = table.clone(REG.fx_oriel_14)
			real.fx_oriel_14.box = { 4, 14, 3.2 }
			real.fx_oriel_14.size = { 4.3, 14, 3.4 }
			real.fx_oriel_14.min = { -2.15, 0, -0.6 }
			local windows, oriels = 0, 0
			for seed = 1, 20 do
				local parts, errors = compile({ house({ seed = seed }) }, real)
				check.equal(#errors, 0)
				for _, p in parts do
					if p.module == "window" or p.module == "windowb" then
						windows += 1
						check.truthy(near(p.size[1], 4) and near(p.size[2], 14) and near(p.size[3], 1.38))
					elseif p.module == "oriel" then
						oriels += 1
						check.truthy(near(p.size[1], 4.3) and near(p.size[3], 3.4))
						-- its box's middle 1.1 in front of the wall's line (the south wall at z = 12)
						check.truthy(near(p.pos[3], 12 + 1.1, 1e-6))
					end
				end
			end
			check.truthy(windows > 60 and oriels >= 3)
		end)

		test.case("a module's face is to the street: what stands proud of it stands OUT of the house", function()
			-- an oriel modelled 3 deep with 2.4 of it in front of the wall's line (its own +Z is its front, as a
			-- skin's is): wherever the door is, its box's middle stands 0.9 outside the wall's line, never inside
			local proud = table.clone(REG)
			proud.fx_oriel_14 = table.clone(REG.fx_oriel_14)
			proud.fx_oriel_14.size = { 4, 14, 3 }
			proud.fx_oriel_14.min = { -2, 0, -0.6 }
			local OUT = { S = { 0, 1 }, N = { 0, -1 }, E = { 1, 0 }, W = { -1, 0 } }
			local found = 0
			for seed = 1, 40 do
				for side, out in OUT do
					local parts = compile(
						{ house({ seed = seed, floors = 2, door = { side = side, width = 5, height = 8.5 } }) },
						proud
					)
					for _, p in parts do
						if p.module == "oriel" then
							found += 1
							local wall = if side == "S" or side == "N" then 12 else 11.5 -- (the wall's line from the middle)
							local d = p.pos[1] * out[1] + p.pos[3] * out[2]
							check.truthy(near(d, wall + 0.9, 1e-6))
						end
					end
				end
			end
			check.truthy(found >= 20)
		end)

		test.case(
			"a module that is missing or cut for another opening is said ONCE and the houses are built plain",
			function()
				local short = table.clone(REG)
				short.fx_wall_14 = nil
				local parts, errors =
					compile({ house(), house({ center = { 60, 0, 0 } }), house({ center = { 120, 0, 0 } }) }, short)
				check.equal(#errors, 1)
				check.truthy(string.find(errors[1].message, 'no world mesh "fx_wall_14"', 1, true))
				local walls = 0
				for _, p in parts do
					check.truthy(p.mesh == nil)
					if p.name == "Wall" then
						walls += 1
						check.equal(p.transparency, 0)
					end
				end
				check.truthy(walls > 30)
				-- a door cut 6 wide in the mesh, 5 in the house
				local wide = table.clone(REG)
				wide.fx_door_14 = table.clone(REG.fx_door_14)
				wide.fx_door_14.gap = { width = 6, height = 8.5, sill = 0 }
				local _, doorErrors = compile({ house() }, wide)
				check.equal(#doorErrors, 1)
				check.truthy(string.find(doorErrors[1].message, "opening has width 6, the house's 5", 1, true))
				-- a skin and a facade on one building
				local withSkin = table.clone(REG)
				withSkin.fx_whole = {
					size = { 25, 40, 26 },
					min = { -12.5, 0, -13 },
					footprint = { 23, 24 },
					floors = 2,
					floorHeight = 14,
				}
				local bothParts, both = compile({ house({ skin = "fx_whole" }) }, withSkin)
				for _, p in bothParts do
					check.truthy(p.mesh == nil) -- (neither: which was meant is not the compiler's to guess)
					if p.name == "Wall" then
						check.equal(p.transparency, 0)
					end
				end
				local said = false
				for _, e in both do
					said = said
						or string.find(
								e.message,
								'a "skin" (one whole mesh) or a "facade" (modules), not both',
								1,
								true
							)
							~= nil
				end
				check.truthy(said)
			end
		)
	end)

	test.suite("Facade grammar: a town made of modules", function()
		local function spec(seed: number, more: any?): any
			local s: any = {
				center = { 0, 0, 0 },
				area = { 256, 224 },
				seed = seed,
				gates = { "S" },
				mats = MATS,
				bend = 0,
				skins = "tw",
				facade = true,
			}
			for k, v in more or {} do
				s[k] = v
			end
			return s
		end

		test.case(
			'"facade": true gives every house the modules\' prefix and its own seed; false, its whole mesh',
			function()
				for seed = 1, 4 do
					local s = spec(seed)
					local seeds, houses = {}, 0
					for _, st in Town.steps(Town.plan(s), s) do
						local b = st.building
						if b then
							houses += 1
							check.equal(b.facade, "tw")
							check.equal(b.skin, nil)
							check.equal(seeds[b.seed], nil) -- (no two houses one seed)
							seeds[b.seed] = true
						end
					end
					check.truthy(houses > 30)
					local whole = spec(seed, { facade = false })
					for _, st in Town.steps(Town.plan(whole), whole) do
						local b = st.building
						if b then
							check.equal(b.facade, nil)
							check.equal(b.seed, nil)
							check.truthy(string.sub(b.skin, 1, 3) == "tw_")
						end
					end
				end
			end
		)

		test.case('what "facade" refuses', function()
			local function errorsOf(s: any): string
				local out = {}
				for _, i in Town.plan(s).issues do
					if i.severity == "error" then
						table.insert(out, i.message)
					end
				end
				return table.concat(out, "\n")
			end
			check.equal(errorsOf(spec(1)), "")
			check.equal(errorsOf(spec(1, { facade = false })), "")
			check.truthy(string.find(errorsOf(spec(1, { facade = "yes" })), '"facade" is true', 1, true))
			check.truthy(string.find(errorsOf(spec(1, { facade = 1 })), '"facade" is true', 1, true))
			local bare = spec(1)
			bare.skins = nil
			check.truthy(string.find(errorsOf(bare), '"facade": true needs "skins"', 1, true))
		end)

		test.case(
			"the town's kit is 8 or 13 modules where it was 30 and more house meshes; every house fits it",
			function()
				for seed = 1, 4 do
					local s = spec(seed)
					local plan = Town.plan(s)
					local kit, problem = Town.kit(plan, s)
					check.equal(problem, nil)
					local whole = spec(seed, { facade = false })
					local houses = Town.kit(Town.plan(whole), whole)
					check.truthy(#kit == 8 or #kit == 13)
					check.truthy(#houses >= 25)
					local record = Town.record("T", plan)
					check.equal(record.modules, #kit)
					check.equal(Town.record("T", Town.plan(whole)).modules, nil)
					-- the whole town compiled on that kit: no fault, every house in modules, and far fewer meshes than types
					local _, parts, issues = World.compile(
						{ name = "T", palette = PALETTE, scale = "r6", build = { { town = s } } },
						{ meshes = registry(kit) }
					)
					for _, i in issues do
						check.truthy(i.severity ~= "error")
					end
					local used, placed = {}, 0
					for _, p in parts do
						if p.mesh then
							used[p.mesh] = true
							placed += 1
						end
					end
					local n = 0
					for name in used do
						n += 1
						check.truthy(string.sub(name, 1, 3) == "tw_")
					end
					check.truthy(n >= 6 and n <= #kit)
					check.truthy(placed > 1000)
				end
			end
		)

		test.case("in a bent town and on a slope every window module still stands on its own sill", function()
			for _, more in { { bend = 8 }, { slope = { rise = 6, toward = "N" } } } do
				local s = spec(2, more)
				local kit = Town.kit(Town.plan(s), s)
				local _, parts, issues = World.compile(
					{ name = "T", palette = PALETTE, scale = "r6", build = { { town = s } } },
					{ meshes = registry(kit) }
				)
				for _, i in issues do
					check.truthy(i.severity ~= "error")
				end
				local sills = {}
				for _, p in parts do
					if p.name == "Sill" then
						sills[string.format("%.3f %.3f %.3f", p.pos[1], p.pos[2] - p.size[2] / 2, p.pos[3])] = true
					end
				end
				local windows = 0
				for _, p in parts do
					if p.module == "window" or p.module == "windowb" or p.module == "oriel" then
						windows += 1
						check.truthy(
							sills[string.format("%.3f %.3f %.3f", p.pos[1], p.pos[2] - p.size[2] / 2, p.pos[3])]
						)
					end
				end
				check.truthy(windows > 150)
			end
		end)

		test.case("two towns of one blueprint do not wear the same run of windows", function()
			local function run(seed: number, center: { number }): string
				local s = spec(seed, { center = center })
				local out = {}
				for _, st in Town.steps(Town.plan(s), s) do
					local b = st.building
					if b and #out < 40 then
						local win, oriel = Facade.pick(b.seed, b.floors)
						table.insert(out, (if win == "window" then "w" else "b") .. (if oriel then "O" else "-"))
					end
				end
				return table.concat(out, " ")
			end
			check.truthy(run(1, { 0, 0, 0 }) ~= run(7, { 0, 0, 0 }))
			check.truthy(run(1, { 0, 0, 0 }) ~= run(1, { 600, 0, 0 }))
			check.equal(run(3, { 0, 0, 0 }), run(3, { 0, 0, 0 }))
		end)

		test.case("two houses of one TYPE can differ (they could not with one mesh a type)", function()
			local s = spec(2)
			local byType: { [string]: { [string]: boolean } } = {}
			local whole = spec(2, { facade = false })
			local types = {}
			for _, st in Town.steps(Town.plan(whole), whole) do
				if st.building then
					table.insert(types, st.building.skin)
				end
			end
			local k = 0
			for _, st in Town.steps(Town.plan(s), s) do
				local b = st.building
				if b then
					k += 1
					local win, oriel = Facade.pick(b.seed, b.floors)
					byType[types[k]] = byType[types[k]] or {}
					byType[types[k]][`{win}{if oriel then "+oriel" else ""}`] = true
				end
			end
			local mixed = 0
			for _, looks in byType do
				local n = 0
				for _ in looks do
					n += 1
				end
				mixed += if n > 1 then 1 else 0
			end
			check.truthy(mixed >= 5)
		end)
	end)

	-- the W3 kit (kit/world/modkit_facade.py; the owner, 2026-11-23: "keep rolling straight through W3 GothicCourtyard
	-- swap"): modules on the two shared trim sheets, a SurfaceAppearance each from the sheets' uploaded maps, the
	-- meshes on a module's other sheet placed with it, a quoin up every corner
	test.suite("Facade grammar: a house of the W3 kit", function()
		local W3 = table.clone(LOOK)
		W3.kit = "w3"
		local recipes = Facade.kit(W3)
		-- as kit world meshes files a W3 kit: each module its sheet, a window / an oriel its glass on the other
		-- sheet (a part of its own), the roof its gables
		local function w3registry(): any
			local reg = registry(recipes)
			for _, r in recipes do
				local e = reg[r.name]
				e.kit, e.trim, e.parts = "w3", if r.module == "roof" then "roof" else "stone", {}
				if r.module == "window" or r.module == "windowb" or r.module == "oriel" or r.module == "roof" then
					local part = `{r.name}__{if r.module == "roof" then "stone" else "roof"}`
					reg[part] = {
						kind = "gothic_module_part",
						trim = if r.module == "roof" then "stone" else "roof",
						size = r.size,
						min = { -r.size[1] / 2, 0, -r.size[3] / 2 },
					}
					table.insert(e.parts, part)
				end
			end
			return reg
		end
		local MAPS = {
			kit_trim_stone_color = "rbxassetid://11",
			kit_trim_stone_normal = "rbxassetid://12",
			kit_trim_stone_roughness = "rbxassetid://13",
			kit_trim_roof_color = "rbxassetid://21",
			kit_trim_roof_normal = "rbxassetid://22",
			kit_trim_roof_roughness = "rbxassetid://23",
		}
		local function build(ids: any): ({ any }, { any }, { any })
			local bp = { name = "T", palette = PALETTE, scale = "r6", build = { { building = house() } } }
			local _, parts, issues = World.compile(bp, { meshes = w3registry(), ids = ids })
			local errors = {}
			for _, i in issues do
				if i.severity == "error" then
					table.insert(errors, i)
				end
			end
			return parts, errors, issues
		end

		test.case("every recipe says its kit, and a quoin a storey height joins them", function()
			local quoins = 0
			for _, r in recipes do
				check.equal(r.kit, "w3")
				if r.module == "quoin" then
					quoins += 1
					check.equal(r.floorHeight, 14)
				end
			end
			check.equal(quoins, 1)
			for _, r in Facade.kit(LOOK) do -- (no kit: no field, no quoin - gothic_blender's modules as before)
				check.equal(r.kit, nil)
				check.truthy(r.module ~= "quoin")
			end
		end)

		test.case(
			"with the sheets uploaded each module wears its sheet's three maps; its companions stand with it",
			function()
				local parts, errors = build({ worldtextures = MAPS })
				check.equal(#errors, 0)
				local count: { [string]: number } = {}
				for _, p in parts do
					if p.mesh then
						count[p.mesh] = (count[p.mesh] or 0) + 1
						local reg = w3registry()[p.mesh]
						local sa = nil
						for _, c in p.children or {} do
							if c.kind == "surface" then
								sa = c
							end
						end
						check.truthy(sa ~= nil)
						local sheet = reg.trim
						check.equal(sa.maps.ColorMap, MAPS[`kit_trim_{sheet}_color`])
						check.equal(sa.maps.NormalMap, MAPS[`kit_trim_{sheet}_normal`])
						check.equal(sa.maps.RoughnessMap, MAPS[`kit_trim_{sheet}_roughness`])
					end
				end
				check.truthy((count.fx_roof or 0) > 0)
				check.truthy((count.fx_window_14 or 0) + (count.fx_windowb_14 or 0) > 0)
				for _, kind in { "window_14", "windowb_14", "roof" } do
					local name = `fx_{kind}`
					local other = `{name}__{if kind == "roof" then "stone" else "roof"}`
					check.equal(count[other], count[name])
				end
				-- a quoin up each of the four corners of each of the two storeys (no opening within its reach here)
				check.equal(count.fx_quoin_14, 8)
			end
		)

		test.case("a sheet not uploaded: no SurfaceAppearance at all, the maps named once", function()
			local parts, errors, issues = build({ worldtextures = {} })
			check.equal(#errors, 0)
			for _, p in parts do
				for _, c in p.children or {} do
					check.truthy(c.kind ~= "surface")
				end
			end
			local said = 0
			for _, i in issues do
				if string.find(i.message, "trim map(s) not uploaded", 1, true) then
					said += 1
					check.truthy(string.find(i.message, "kit_trim_stone_color", 1, true) ~= nil)
				end
			end
			check.equal(said, 1)
		end)

		test.case("a module whose companion is not made is said, and the house is built plain", function()
			local reg = w3registry()
			reg["fx_window_14__roof"], reg["fx_windowb_14__roof"] = nil, nil
			local bp = { name = "T", palette = PALETTE, scale = "r6", build = { { building = house() } } }
			local _, parts, issues = World.compile(bp, { meshes = reg, ids = { worldtextures = MAPS } })
			local said = false
			for _, i in issues do
				said = said or string.find(i.message, '__roof" is not in the registry', 1, true) ~= nil
			end
			check.truthy(said)
			for _, p in parts do
				check.truthy(p.mesh == nil)
			end
		end)
	end)

	test.suite("kit world facade: one prefix is one kit", function()
		-- (the 2026-11-23 review: a second house of the prefix with another wall thickness got the first house's
		-- modules, its invisible collision wall standing 0.4 st proud of the stone you see)
		local DIR = "build/_spec_facade_kit"
		local function facadeHouse(name: string, thickness: number): any
			return {
				building = {
					name = name,
					center = { 0, 0, 0 },
					size = { 20, 20 },
					floors = 2,
					floorHeight = 14,
					thickness = thickness,
					facade = "gc_spec",
					door = { side = "S", width = 5, height = 9 },
					windows = { every = 10, width = 3.4, height = 7, sill = 3.5 },
				},
			}
		end
		local function run(build: { any }): any
			if fs.isDir(DIR) then
				fs.removeDir(DIR)
			end
			fs.writeDir(DIR)
			local path = `{DIR}/Spec.json`
			fs.writeFile(path, serde.encode("json", { name = "Spec", build = build }))
			local was = Run.expectingFailure
			Run.expectingFailure = true
			local step = WorldCmd.facadeKit(path, "w3", `{DIR}/meshes`)
			Run.expectingFailure = was
			fs.removeDir(DIR)
			return step
		end
		test.case("two houses of one prefix with ONE wall thickness: the kit is written", function()
			local step = run({ facadeHouse("A", 1.2), facadeHouse("B", 1.2) })
			check.truthy(step.ok)
		end)
		test.case("a second house with another wall thickness is refused, by name", function()
			local step = run({ facadeHouse("A", 1.2), facadeHouse("B", 2) })
			check.truthy(not step.ok)
			check.truthy(string.find(step.tail, 'building "B": its wall thickness is 2', 1, true) ~= nil)
		end)
	end)
end
