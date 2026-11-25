-- interior.spec.luau — furnished rooms by rules (kit/lib/interior): every kind, many room sizes, every rule holds;
-- the stair lane, the door and the windows are respected; the check catches a broken layout.
local frk = require("../frk")
local test, check = frk.test, frk.check

local Interior = require("../../lib/interior")

local function room(w: number, d: number, clear: { any }?, windows: { any }?): Interior.Room
	return { x0 = 0, x1 = w, z0 = 0, z1 = d, y = 10, height = 13, clear = clear or {}, windows = windows or {} }
end

local function names(pieces: { Interior.Piece }): string
	local out = {}
	for _, p in pieces do
		table.insert(out, p.name)
	end
	table.sort(out)
	return table.concat(out, ",")
end

return function()
	test.suite("Interior", function()
		test.case("every kind, every size: no rule broken, furniture on the floor", function()
			for _, kind in Interior.KINDS do
				for _, size in { { 20, 14 }, { 42, 28 }, { 30, 30 }, { 16, 40 } } do
					local r = room(size[1], size[2])
					local pieces = Interior.layout(r, kind, 1)
					check.equal(#Interior.check(r, pieces), 0)
					check.is_true(#pieces >= 2)
					for _, p in pieces do
						check.equal(p.pos[2] - p.size[2] / 2, 10) -- (stands on the floor)
					end
				end
			end
		end)
		test.case("a big hall gets its long table and benches down the middle, and a lit hearth", function()
			local pieces = Interior.layout(room(42, 28), "hall", 0)
			local n = names(pieces)
			check.is_true(string.find(n, "Bench,Bench", 1, true) ~= nil)
			check.is_true(string.find(n, "Table", 1, true) ~= nil)
			local hearth = nil
			for _, p in pieces do
				if p.name == "Hearth" then
					hearth = p
				end
			end
			check.not_nil(hearth)
			check.is_true((hearth :: any).light == true)
		end)
		test.case("a hearth faces the door from the opposite wall; an upper room gets a walk-over rug", function()
			for _, side in { "N", "E", "S", "W" } do
				local r = room(42, 28)
				r.door = side
				local hearth = nil
				for _, p in Interior.layout(r, "hall", 3) do
					if p.name == "Hearth" then
						hearth = Interior.footprint(p)
					end
				end
				check.not_nil(hearth)
				local h = hearth :: Interior.Rect
				local opposite = if side == "N"
					then h.z1 >= 28 - 1e-6
					elseif side == "S" then h.z0 <= 1e-6
					elseif side == "E" then h.x0 <= 1e-6
					else h.x1 >= 42 - 1e-6
				check.is_true(opposite)
			end
			local rug = nil
			local pieces = Interior.layout(room(42, 28), "chamber", 1)
			for _, p in pieces do
				if p.name == "Rug" then
					rug = p
				end
			end
			check.not_nil(rug)
			check.is_true((rug :: any).flat == true)
			check.equal(#Interior.check(room(42, 28), pieces), 0)
		end)
		test.case("nothing on the stair lane or in the door's clearance", function()
			local stairs = { x0 = 1, x1 = 6, z0 = 0, z1 = 28 }
			local door = { x0 = 16, x1 = 26, z0 = 21, z1 = 28 }
			local r = room(42, 28, { stairs, door })
			for _, kind in Interior.KINDS do
				for _, p in Interior.layout(r, kind, 2) do
					local fp = Interior.footprint(p)
					check.is_false(Interior.overlaps(fp, stairs))
					check.is_false(Interior.overlaps(fp, door))
				end
			end
		end)
		test.case("nothing taller than a sill stands under a window", function()
			-- windows along the whole north wall: tall pieces must go elsewhere
			local r = room(30, 20, {}, { { side = "N", from = 0, to = 30, sill = 4 } })
			for _, p in Interior.layout(r, "chamber", 0) do
				local fp = Interior.footprint(p)
				if fp.z0 <= 1e-6 then -- (against the north wall)
					check.is_true(p.size[2] <= 4)
				end
			end
		end)
		test.case("the check catches a piece in a walkway, in a clear zone, through a wall", function()
			local r = room(20, 20, { { x0 = 15, x1 = 20, z0 = 15, z1 = 20 } })
			local bad = {
				{
					name = "Shelf",
					role = "wood",
					size = { 6, 8, 2 },
					pos = { 10, 14, 1 },
					front = { x0 = 7, x1 = 13, z0 = 2, z1 = 6 },
				},
				{ name = "Crate", role = "wood", size = { 3, 3, 3 }, pos = { 10, 11.5, 4 } }, -- (in the shelf's walkway)
				{ name = "Chest", role = "wood", size = { 3, 3, 3 }, pos = { 17, 11.5, 17 } }, -- (in the clear zone)
				{ name = "Bed", role = "cloth", size = { 4, 2, 8 }, pos = { 1, 11, 10 } }, -- (through the west wall)
			}
			local problems = table.concat(Interior.check(r, bad), " | ")
			check.is_true(string.find(problems, "walkway", 1, true) ~= nil)
			check.is_true(string.find(problems, "stair lane / door", 1, true) ~= nil)
			check.is_true(string.find(problems, "through a wall", 1, true) ~= nil)
		end)
		test.case("an unknown kind or a tiny room furnishes nothing rather than break a rule", function()
			check.equal(#Interior.layout(room(20, 20), "throne", 0), 0)
			local tiny = room(5, 5)
			for _, kind in Interior.KINDS do
				check.equal(#Interior.check(tiny, Interior.layout(tiny, kind, 0)), 0)
			end
		end)
	end)

	-- A BODY CAN WALK IT (Interior.walk; the owner's limitations list, W-R06). The rooms here are typed by hand so
	-- the answer is known without the rule: where the gap is, how wide it is.
	test.suite("Interior: a body can walk the room", function()
		local DOOR = { x0 = 7, x1 = 13, z0 = 13, z1 = 20 } -- (a door in the south wall of a 20 x 20 room)
		local function piece(name: string, x0: number, x1: number, z0: number, z1: number, front: any?): any
			return {
				name = name,
				role = "wood",
				size = { x1 - x0, 3, z1 - z0 },
				pos = { (x0 + x1) / 2, 11.5, (z0 + z1) / 2 },
				front = front,
			}
		end

		test.case("a piece whose open side is shut in by its neighbours cannot be reached", function()
			local r = room(20, 20, { DOOR })
			-- a chest against the north wall, its walkway (z 3..7) boxed by a crate each side and one across its mouth
			-- further out: no rectangle rule is broken (nothing stands IN the walkway), yet no body gets to it
			local chest = piece("Chest", 8, 12, 0, 3, { x0 = 8, x1 = 12, z0 = 3, z1 = 7 })
			local boxed = {
				chest,
				piece("Crate", 4, 8, 0, 9),
				piece("Crate", 12, 16, 0, 9),
				piece("Crate", 6, 14, 7, 9.5),
			}
			local w = Interior.walk(r, boxed)
			check.equal(#w.shut, 1)
			check.equal(w.shut[1], 1)
			local problems = table.concat(Interior.check(r, boxed), " | ")
			check.is_true(string.find(problems, "Chest 1 cannot be reached", 1, true) ~= nil)
			check.is_true(string.find(problems, "2.5 studs wide", 1, true) ~= nil)
			-- the crate across its mouth moved 3 studs aside: a way in, and nothing to say
			boxed[4] = piece("Crate", 14, 19, 9.5, 12)
			check.equal(#Interior.walk(r, boxed).shut, 0)
			-- (nothing to say about reaching it; this hand-typed room still breaks the later rules - the moved crate
			-- stands half a stud from its neighbour, a sliver - and the check says that, and only that kind)
			local after = table.concat(Interior.check(r, boxed), " | ")
			check.equal(string.find(after, "cannot be reached", 1, true), nil)
			check.truthy(string.find(after, "never a sliver", 1, true) ~= nil)
		end)

		test.case("a gap a body does not fit through is no way: 2 studs shut, 3 studs open", function()
			local r = room(20, 20, { DOOR })
			local chest = piece("Chest", 8, 12, 0, 3, { x0 = 8, x1 = 12, z0 = 3, z1 = 7 })
			for _, gap in { 0.5, 1, 2, 2.4 } do
				-- two crates across the room at z 8..10 with `gap` between them, each run to its wall
				local row = { chest, piece("Crate", 0, 10 - gap / 2, 8, 10), piece("Crate", 10 + gap / 2, 20, 8, 10) }
				check.equal(#Interior.walk(r, row).shut, 1)
			end
			-- (walked on a half-stud grid: a gap of a body and one cell, 3 studs, always passes; between 2.5 and 3 it
			-- depends on where the gap falls on the grid, and the rule then errs to "shut")
			for _, gap in { 3, 3.4, 5 } do
				local row = { chest, piece("Crate", 0, 10 - gap / 2, 8, 10), piece("Crate", 10 + gap / 2, 20, 8, 10) }
				check.equal(#Interior.walk(r, row).shut, 0)
			end
			-- ... and a gap between a piece and a WALL counts the same (the body must fit beside it)
			check.equal(#Interior.walk(r, { chest, piece("Crate", 2, 20, 8, 10) }).shut, 1)
			check.equal(#Interior.walk(r, { chest, piece("Crate", 3, 20, 8, 10) }).shut, 0)
		end)

		test.case("a row of pieces between the door and the stairs cuts the room in two", function()
			local stairs = { x0 = 0.5, x1 = 5.5, z0 = 0, z1 = 6 }
			local r = room(20, 20, { DOOR, stairs })
			local wall = { piece("Crate", 0, 10, 8, 10), piece("Crate", 10, 20, 8, 10) }
			local w = Interior.walk(r, wall)
			check.equal(#w.cut, 1)
			check.equal(w.cut[1], 2)
			local problems = table.concat(Interior.check(r, wall), " | ")
			check.is_true(string.find(problems, "the room is cut in two", 1, true) ~= nil)
			check.is_true(string.find(problems, "to way 2", 1, true) ~= nil)
			check.equal(#Interior.walk(r, { wall[1] }).cut, 0)
			-- a rug across the same line is walked over
			local rug = piece("Rug", 0, 20, 8, 10)
			rug.flat = true
			check.equal(#Interior.walk(r, { rug }).cut, 0)
			check.equal(Interior.walk(r, { rug }).open, 1)
		end)

		test.case("how much floor is open, and a room packed past it", function()
			local r = room(20, 20, { DOOR })
			check.equal(Interior.walk(r, {}).open, 1)
			check.is_true(math.abs(Interior.walk(r, { piece("Crate", 0, 10, 0, 10) }).open - 0.75) < 1e-9)
			-- three quarters of the floor under crates: 25% open, under the 30% a room keeps
			local packed = { piece("Crate", 0, 20, 0, 8), piece("Crate", 0, 6, 8, 20), piece("Crate", 14, 20, 8, 20) }
			local w = Interior.walk(r, packed)
			check.is_true(w.open < 0.3)
			check.is_true(
				string.find(table.concat(Interior.check(r, packed), " | "), "of the floor is open", 1, true) ~= nil
			)
			check.is_true(#Interior.check(r, { packed[1] }) == 0)
		end)

		test.case("a piece is reached at its OPEN side: free floor beside it is no use if its mouth is shut", function()
			local r = room(20, 20, { DOOR })
			-- a chest against the north wall with open floor either side of it and a crate right across its mouth
			-- (in no walkway: the chest's own runs z 3..7, the crate stands z 7..9.5 from wall... to wall of its bay)
			local chest = piece("Chest", 8, 12, 0, 3, { x0 = 8, x1 = 12, z0 = 3, z1 = 7 })
			local lid = { chest, piece("Crate", 5, 15, 3, 5) }
			lid[2].pos[3] = 4 -- (z 3..5: hard against the chest's face)
			local w = Interior.walk(r, lid)
			check.equal(#w.shut, 1)
			-- the same crate a body's width further out: the chest's mouth is open
			check.equal(#Interior.walk(r, { chest, piece("Crate", 5, 15, 7.5, 9.5) }).shut, 0)
		end)

		test.case("the walk starts at the DOOR, though the compiler lists the stair lane first", function()
			local stairs = { x0 = 0.5, x1 = 5.5, z0 = 0, z1 = 20 } -- (a lane the whole depth of the room: it touches every wall)
			local r = room(20, 20, { stairs, DOOR })
			r.door = "S"
			local w = Interior.walk(r, {})
			check.equal(w.from, 2)
			check.equal(#w.cut, 0)
			-- a wall of crates shuts the door's corner off from the rest: it is the STAIRS that are cut off from the door
			local pen = { piece("Crate", 5.5, 20, 9, 11), piece("Crate", 5.5, 7.5, 11, 20) }
			local cutOff = Interior.walk(r, pen)
			check.equal(cutOff.from, 2)
			check.equal(table.concat(cutOff.cut, ","), "1")
			check.is_true(
				string.find(table.concat(Interior.check(r, pen), " | "), "from its way in (way 2) to way 1", 1, true)
					~= nil
			)
			-- no door named: the first way in
			r.door = nil
			check.equal(Interior.walk(r, {}).from, 1)
		end)

		test.case("a way in no body fits in, and floor walled off behind furniture, are both said", function()
			-- a second way in (the stairs' landing) with a crate standing right over it: nobody can stand in it
			local r = room(20, 20, { DOOR, { x0 = 0, x1 = 5, z0 = 0, z1 = 5 } })
			local over = { piece("Crate", 0, 7, 0, 7) }
			local w = Interior.walk(r, over)
			check.equal(table.concat(w.tight, ","), "2")
			check.equal(#Interior.walk(r, {}).tight, 0)
			check.is_true(
				string.find(table.concat(Interior.check(r, over), " | "), "way 2 into the room", 1, true) ~= nil
			)
			-- crates with no walkway of their own wall off the north half: no piece is shut in, no way is cut, 70% of
			-- the floor is open - and half of what a body could stand on cannot be got to
			local plain = room(20, 20, { DOOR })
			local row = { piece("Crate", 0, 10, 8, 10), piece("Crate", 10, 20, 8, 10) }
			local lost = Interior.walk(plain, row)
			check.equal(#lost.shut + #lost.cut, 0)
			check.is_true(lost.open > 0.7)
			check.is_true(lost.lost > 0.3 and lost.lost < 0.6)
			check.is_true(
				string.find(
					table.concat(Interior.check(plain, row), " | "),
					"is walled off from the room's way in",
					1,
					true
				) ~= nil
			)
			-- one crate of the two: nothing walled off
			check.equal(Interior.walk(plain, { row[1] }).lost, 0)
			check.equal(#Interior.check(plain, { row[1] }), 0)
		end)

		test.case("a room with no door named is walked from its door's wall, or its middle", function()
			local r = room(20, 20)
			r.door = "S"
			local chest = piece("Chest", 8, 12, 0, 3, { x0 = 8, x1 = 12, z0 = 3, z1 = 7 })
			check.equal(#Interior.walk(r, { chest }).shut, 0)
			check.equal(#Interior.walk(r, { chest, piece("Crate", 0, 20, 8, 10) }).shut, 1)
			-- (the same wall of crates with the door on the chest's own side: it is reached)
			r.door = "N"
			check.equal(#Interior.walk(r, { chest, piece("Crate", 0, 20, 8, 10) }).shut, 0)
		end)

		test.case(
			"every room the rules furnish can be walked: from the door to each piece and to the stairs",
			function()
				local rooms, pieces, withStairs = 0, 0, 0
				for w = 12, 44, 8 do
					for d = 12, 40, 4 do
						for _, kind in Interior.KINDS do
							for seed = 0, 2 do
								for _, stairs in { false, true } do
									local clear = { { x0 = w / 2 - 3.5, x1 = w / 2 + 3.5, z0 = d - 7, z1 = d } }
									if stairs then
										table.insert(clear, { x0 = 0.5, x1 = 5.5, z0 = -3, z1 = 1 + 14 * 1.8 + 4 })
										withStairs += 1
									end
									local r = room(w, d, clear)
									r.door = "S"
									local out = Interior.layout(r, kind, seed)
									rooms += 1
									pieces += #out
									check.equal(table.concat(Interior.check(r, out), " | "), "")
									local walked = Interior.walk(r, out)
									check.equal(#walked.shut + #walked.cut, 0)
									check.is_true(walked.open >= 0.3)
								end
							end
						end
					end
				end
				check.is_true(
					rooms == 240 * #Interior.KINDS
						and pieces > 1000 * #Interior.KINDS
						and withStairs == 120 * #Interior.KINDS
				)
				-- what each room is FOR is still there: a bed in every chamber, a hearth in every hall the size of one
				for w = 12, 44, 8 do
					for d = 16, 40, 4 do
						for seed = 0, 2 do
							local r = room(w, d, { { x0 = w / 2 - 3.5, x1 = w / 2 + 3.5, z0 = d - 7, z1 = d } })
							r.door = "S"
							check.is_true(
								string.find(names(Interior.layout(r, "chamber", seed)), "Bed", 1, true) ~= nil
							)
							if w >= 20 and d >= 16 then
								check.is_true(
									string.find(names(Interior.layout(r, "hall", seed)), "Hearth", 1, true) ~= nil
								)
							end
						end
					end
				end
				-- the room the rules shut two pieces into before (a chamber 12 x 16 with a door in its south wall): its
				-- bed is what shut them in, and it still stands - what the room is for goes last
				local small = room(12, 16, { { x0 = 2.5, x1 = 9.5, z0 = 9, z1 = 16 } })
				small.door = "S"
				local got = names(Interior.layout(small, "chamber", 0))
				check.is_true(string.find(got, "Bed", 1, true) ~= nil)
				-- a chamber 12 x 24: a wardrobe and a chest cut it in two behind the second bed. What stood in the way
				-- went, BOTH beds stand (the first cut of this rule took the second bed and kept the wardrobe)
				local long = room(12, 24, { { x0 = 2.5, x1 = 9.5, z0 = 17, z1 = 24 } })
				long.door = "S"
				local kept = names(Interior.layout(long, "chamber", 0))
				check.is_true(string.find(kept, "Bed,Bed", 1, true) ~= nil)
				check.is_true(string.find(kept, "Wardrobe", 1, true) == nil)
			end
		)
	end)

	-- LIMITATIONS_FIXES_V3.md stage D (floor-plan-first zoning): a dining table keeps 6 studs from a hearth and from a
	-- bed, and furniture covers at most 40 % of a room's floor. Measured on the old rules over 972 rooms (3 kinds, 14 to
	-- 30 studs a side, a door on each wall): a hall's table stood 4.5 from its hearth in 18 of 100 halls; rooms were
	-- covered up to 46.6 %.
	test.suite("Interior: zoning", function()
		local function gap(a: any, b: any): number
			local fa, fb = Interior.footprint(a), Interior.footprint(b)
			local dx = math.max(0, math.max(fa.x0, fb.x0) - math.min(fa.x1, fb.x1))
			local dz = math.max(0, math.max(fa.z0, fb.z0) - math.min(fa.z1, fb.z1))
			return math.sqrt(dx * dx + dz * dz)
		end
		local function doorOn(w: number, d: number, side: string): any
			local mid = if side == "N" or side == "S" then w / 2 else d / 2
			if side == "N" then
				return { x0 = mid - 2.5, x1 = mid + 2.5, z0 = 0, z1 = 4 }
			elseif side == "S" then
				return { x0 = mid - 2.5, x1 = mid + 2.5, z0 = d - 4, z1 = d }
			elseif side == "W" then
				return { x0 = 0, x1 = 4, z0 = mid - 2.5, z1 = mid + 2.5 }
			end
			return { x0 = w - 4, x1 = w, z0 = mid - 2.5, z1 = mid + 2.5 }
		end

		test.case("a hall's table stands 6 studs or more from its hearth, and the hall keeps both", function()
			local halls, tables = 0, 0
			for w = 14, 30, 2 do
				for d = 14, 30, 2 do
					for _, side in { "N", "E", "S", "W" } do
						local r = room(w, d, { doorOn(w, d, side) })
						r.door = side
						local pieces = Interior.layout(r, "hall", w + d)
						check.equal(#Interior.check(r, pieces), 0)
						local tbl, hearth = nil, nil
						for _, p in pieces do
							if p.name == "Table" then
								tbl = p
							elseif p.name == "Hearth" then
								hearth = p
							end
						end
						halls += 1
						check.truthy(hearth ~= nil) -- (what a hall is for is never taken out for the rule)
						if tbl and hearth then
							tables += 1
							check.truthy(gap(tbl, hearth) >= 6 - 1e-9)
						end
					end
				end
			end
			check.equal(halls, 324)
			check.equal(tables, 100) -- (as many tables as the old rules set: none dropped for it)
		end)

		test.case("the check says when a table stands too near a hearth or a bed", function()
			local r = room(30, 30)
			local function at(name: string, x0: number, x1: number, z0: number, z1: number): any
				return {
					name = name,
					role = "wood",
					size = { x1 - x0, 3, z1 - z0 },
					pos = { (x0 + x1) / 2, 11.5, (z0 + z1) / 2 },
				}
			end
			local near = Interior.check(r, { at("Table", 10, 20, 10, 14), at("Hearth", 10, 17, 18, 20.5) })
			check.truthy(string.find(table.concat(near, "\n"), "keep 6 apart", 1, true) ~= nil)
			local bed = Interior.check(r, { at("Table", 10, 20, 10, 14), at("Bed", 22, 26.5, 10, 17.5) })
			check.truthy(string.find(table.concat(bed, "\n"), "keep 6 apart", 1, true) ~= nil)
			local far = Interior.check(r, { at("Table", 10, 20, 10, 14), at("Hearth", 10, 17, 20, 22.5) })
			check.equal(string.find(table.concat(far, "\n"), "apart", 1, true), nil)
		end)

		test.case("furniture covers at most 40 % of a room's floor", function()
			check.truthy(Interior.OPEN >= 0.6 - 1e-9)
			for _, kind in Interior.KINDS do
				for w = 14, 30, 2 do
					for d = 14, 30, 2 do
						for _, side in { "N", "E", "S", "W" } do
							local r = room(w, d, { doorOn(w, d, side) })
							r.door = side
							local w2 = Interior.walk(r, Interior.layout(r, kind, w * d))
							check.truthy(w2.open >= 0.6 - 1e-9)
						end
					end
				end
			end
			-- and a room crowded past it is said
			local r = room(10, 10)
			local crowd = {
				{ name = "Crate", role = "wood", size = { 10, 3, 4.5 }, pos = { 5, 11.5, 2.25 } },
			}
			check.truthy(
				string.find(table.concat(Interior.check(r, crowd), "\n"), "of the floor is open", 1, true) ~= nil
			)
		end)

		-- THE SPINE and NO SLIVERS (V3 stage D: "a >= 4.5-stud clear circulation spine, a >= 3.2-stud furniture gap").
		-- The old layouts left 3,973 slivers and 25 broken spines over the 1,215 rooms measured here.
		local function at(name: string, x0: number, x1: number, z0: number, z1: number): any
			return {
				name = name,
				role = "wood",
				size = { x1 - x0, 3, z1 - z0 },
				pos = { (x0 + x1) / 2, 11.5, (z0 + z1) / 2 },
			}
		end

		test.case("two pieces stand flush or 3.2 studs apart, never a sliver between", function()
			check.truthy(Interior.GAP >= 3.2 - 1e-9)
			local r = room(30, 30)
			local function said(a: any, b: any): boolean
				return string.find(table.concat(Interior.check(r, { a, b }), "\n"), "never a sliver", 1, true) ~= nil
			end
			check.is_true(said(at("Crate", 0, 4, 0, 3), at("Barrel", 5, 7.5, 0, 2.5))) -- (1 stud: a sliver)
			check.is_true(said(at("Crate", 0, 4, 0, 3), at("Barrel", 7, 9.5, 0, 2.5))) -- (3 studs: still one)
			check.is_false(said(at("Crate", 0, 4, 0, 3), at("Barrel", 4, 6.5, 0, 2.5))) -- (flush)
			check.is_false(said(at("Crate", 0, 4, 0, 3), at("Barrel", 7.2, 9.7, 0, 2.5))) -- (3.2 apart)
			-- a table and its benches are one group: the sitting gap between them is not a sliver
			local group = { x0 = 0, x1 = 1, z0 = 0, z1 = 1 }
			local t, b = at("Table", 10, 20, 10, 14), at("Bench", 10, 20, 14.6, 16)
			t.front, b.front = group, group
			check.is_false(said(t, b))
		end)

		test.case("a spine 4.5 studs wide crosses the room: a 3-stud gap passes a body, not the spine", function()
			check.truthy(Interior.SPINE >= 4.5 - 1e-9)
			-- a 20 x 20 room, door in the south wall; a wall of furniture across z 9..11 with ONE opening at x 8..8+opening
			local door = { x0 = 7, x1 = 13, z0 = 16, z1 = 20 }
			local function across(opening: number): { any }
				return { at("Cupboard", 0, 8, 9, 11), at("Cupboard", 8 + opening, 20, 9, 11) }
			end
			local r = room(20, 20, { door })
			r.door = "S"
			local narrow = Interior.spine(r, across(3))
			check.is_true(narrow.owed)
			check.is_false(narrow.held) -- (it stops short of the room's middle line: the far half is behind the row)
			check.equal(#Interior.walk(r, across(3)).cut, 0) -- (a 2.5 body still gets through)
			local problems = table.concat(Interior.check(r, across(3)), "\n")
			check.truthy(string.find(problems, "no 4.5-stud spine", 1, true) ~= nil)
			check.is_true(Interior.spine(r, across(5)).held)
			check.equal(string.find(table.concat(Interior.check(r, across(5)), "\n"), "spine", 1, true), nil)
			-- a second way in (the stairs, in the north-west corner) cut off from the door at spine width
			local stairs = { x0 = 0, x1 = 6, z0 = 0, z1 = 6 }
			local r2 = room(20, 20, { door, stairs })
			r2.door = "S"
			local two = Interior.spine(r2, { at("Crate", 0, 7, 8, 10.5), at("Crate", 10.5, 20, 8, 10.5) })
			check.is_false(two.held)
			check.equal(two.cut[1], 2)
		end)

		test.case("a room too narrow for the spine even empty is not held to it", function()
			local r = room(4, 30, { { x0 = 0, x1 = 4, z0 = 26, z1 = 30 } })
			r.door = "S"
			local sp = Interior.spine(r, {})
			check.is_false(sp.owed)
			check.is_true(sp.held)
		end)

		test.case("every generated room: no sliver, the spine held, every rule", function()
			local rooms, slivers = 0, 0
			for _, kind in Interior.KINDS do
				for w = 14, 30, 4 do
					for d = 14, 30, 4 do
						for _, side in { "N", "E", "S", "W", "up" } do
							local clear = { { x0 = 1, x1 = 6, z0 = 2, z1 = d - 2 } } -- (a stair lane on the west wall)
							if side ~= "up" then
								table.insert(clear, 1, doorOn(w, d, side))
							end
							local r = room(w, d, clear)
							r.door = if side == "up" then nil else side
							local pieces = Interior.layout(r, kind, w * d)
							rooms += 1
							check.equal(#Interior.check(r, pieces), 0)
							check.is_true(Interior.spine(r, pieces).held)
							for i, a in pieces do
								for j, b in pieces do
									if
										j > i
										and not a.flat
										and not b.flat
										and not (a.front ~= nil and a.front == b.front)
									then
										local fa, fb = Interior.footprint(a), Interior.footprint(b)
										local dx = math.max(0, math.max(fa.x0, fb.x0) - math.min(fa.x1, fb.x1))
										local dz = math.max(0, math.max(fa.z0, fb.z0) - math.min(fa.z1, fb.z1))
										local g = math.sqrt(dx * dx + dz * dz)
										if g > 0.05 and g < 3.2 - 1e-6 then
											slivers += 1
										end
									end
								end
							end
						end
					end
				end
			end
			check.equal(rooms, #Interior.KINDS * 125)
			check.equal(slivers, 0)
		end)
	end)

	-- ROOM KINDS beyond hall / chamber / store (LIMITATIONS_FIXES_V3.md stage D): each keeps what it is for, under the
	-- same rules (the "every generated room" case above runs them all)
	test.suite("Interior: more room kinds", function()
		test.case("a kitchen keeps its oven, a study its books, a workshop its bench", function()
			local keys = { kitchen = "Oven", study = "Bookcase", workshop = "Workbench" }
			for kind, key in keys do
				check.truthy(table.find(Interior.KINDS, kind) ~= nil, kind)
				for _, size in { { 16, 16 }, { 20, 14 }, { 30, 24 } } do
					local r = room(
						size[1],
						size[2],
						{ { x0 = size[1] / 2 - 3.5, x1 = size[1] / 2 + 3.5, z0 = size[2] - 7, z1 = size[2] } }
					)
					r.door = "S"
					local pieces = Interior.layout(r, kind, 1)
					check.equal(table.concat(Interior.check(r, pieces), " | "), "")
					check.truthy(
						string.find(names(pieces), key, 1, true) ~= nil,
						`{kind} {size[1]}x{size[2]}: {names(pieces)}`
					)
					check.truthy(#pieces >= 3, `{kind}: {names(pieces)}`)
				end
			end
			-- the oven is lit, and faces the door (the wall opposite it)
			local r = room(20, 20, { { x0 = 6.5, x1 = 13.5, z0 = 13, z1 = 20 } })
			r.door = "S"
			for _, p in Interior.layout(r, "kitchen", 0) do
				if p.name == "Oven" then
					check.is_true(p.light == true)
					check.truthy(p.pos[3] < 5, `oven at z {p.pos[3]}`)
				end
			end
		end)
	end)
end
