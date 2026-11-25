-- interiorv2.spec.luau (kit) — FURNITURE BY ROOM and three more room kinds (LIMITATIONS_FIXES_V4 5.1 / 13.5,
-- interior_v2: "Interior.KINDS (6 rooms) lacks stair_shaft / landing / sanctum & BSP room graphs"). A house whose
-- floors are cut into rooms by the binary split (kit/lib/worldrooms.luau) had its furniture LEFT OUT ("furniture by
-- room is not built yet"); with "interior": { "byRoom": true } each room is furnished on its own: its kind from
-- Interior.program (the biggest room the floor's main use, the smallest one open to the stair hall its stair_shaft /
-- landing, the top floor of three a sanctum), inside its partitions, every doorway a way in kept clear.
-- Held here over many houses (sizes, seeds, 2 and 3 floors): every room is furnished and passes Interior.check (the
-- spine, the gaps, the open floor, a body reaches every piece); no piece crosses a partition or stands in a
-- doorway's clearance; the kinds follow the program; "interior": true with rooms still leaves it out, said.
-- Not claimed: how the rooms look (primitive blocks until the W3 kit's furniture meshes), not seen in Studio.
local frk = require("../frk")
local test, check = frk.test, frk.check

local Interior = require("../../lib/interior")
local World = require("../../lib/world")

local PALETTE = {
	wall = { material = "Brick", color = { 140, 120, 104 } },
	wood = { material = "Wood", color = { 90, 60, 40 } },
	cloth = { material = "Fabric", color = { 110, 30, 30 } },
	metal = { material = "Metal", color = { 60, 60, 64 } },
	fire = { material = "Neon", color = { 255, 140, 60 } },
}

local function house(more: any?): any
	local b: any = {
		name = "House",
		center = { 0, 0, 0 },
		size = { 34, 38 },
		floors = 2,
		mat = "wall",
		roof = "gable",
		stairs = true,
		rooms = true,
		interior = { byRoom = true },
		door = { side = "S", width = 5, height = 8.5 },
	}
	for k, v in more or {} do
		b[k] = v
	end
	return b
end

local function compile(build: { any }): ({ any }, { string }, any, { any })
	local _, parts, issues, extras = World.compile({ name = "T", palette = PALETTE, build = build })
	local errs = {}
	for _, i in issues do
		if i.severity == "error" then
			table.insert(errs, `{i.path}: {i.message}`)
		end
	end
	return parts, errs, extras, issues
end

local FURNITURE = {}
for _, n in
	{
		"Hearth",
		"Cupboard",
		"Candelabra",
		"Barrel",
		"Bench",
		"Table",
		"Bed",
		"Wardrobe",
		"Shelf",
		"Desk",
		"Chest",
		"WeaponRack",
		"ArmorStand",
		"Crate",
		"Sack",
		"Oven",
		"Worktable",
		"Bookcase",
		"Lectern",
		"Workbench",
		"ToolRack",
		"Anvil",
		"SideTable",
		"Altar",
		"Pew",
		"Rug",
	}
do
	FURNITURE[n] = true
end

return function()
	test.suite("Interior v2: three more kinds, furniture by room", function()
		test.case("nine kinds; the three new ones furnish every size and keep every rule", function()
			check.equal(#Interior.KINDS, 9)
			for _, k in { "stair_shaft", "landing", "sanctum" } do
				check.truthy(table.find(Interior.KINDS, k), k)
				for _, size in { { 12, 10 }, { 20, 14 }, { 30, 30 }, { 16, 40 } } do
					local r: Interior.Room = {
						x0 = 0,
						x1 = size[1],
						z0 = 0,
						z1 = size[2],
						y = 0,
						height = 13,
						clear = {},
						windows = {},
						door = "S",
					}
					local pieces = Interior.layout(r, k, 2)
					check.equal(#Interior.check(r, pieces), 0)
					check.truthy(#pieces >= 2, `{k} {size[1]}x{size[2]}: {#pieces} pieces`)
				end
			end
			-- a sanctum's altar is what it is for: it faces the door from the far wall, lit
			local r: Interior.Room =
				{ x0 = 0, x1 = 24, z0 = 0, z1 = 30, y = 0, height = 13, clear = {}, windows = {}, door = "S" }
			local altar = nil
			for _, p in Interior.layout(r, "sanctum", 1) do
				if p.name == "Altar" then
					altar = p
				end
			end
			check.truthy(altar ~= nil, "an altar")
			check.truthy(Interior.footprint(altar :: any).z0 <= 1e-6, "on the wall opposite the door (N)")
			check.truthy((altar :: any).flame == true, "lit")
		end)

		test.case("the program: the biggest room the floor's use, the stair's room its shaft or landing", function()
			local rooms = {
				{ area = 300, openToHall = true },
				{ area = 120, openToHall = true },
				{ area = 200, openToHall = false },
			}
			local k = Interior.program(rooms, 0, 2, true)
			check.equal(k[1], "hall")
			check.equal(k[2], "stair_shaft")
			check.equal(k[3], "kitchen")
			k = Interior.program(rooms, 1, 2, true)
			check.equal(k[1], "chamber")
			check.equal(k[2], "landing")
			k = Interior.program(rooms, 2, 3, false)
			check.equal(k[1], "sanctum")
			check.equal(k[3], "chamber")
			check.equal(k[2], "study")
			-- two rooms: no stair room is given up to passing through
			k = Interior.program({ { area = 100, openToHall = true }, { area = 90, openToHall = true } }, 0, 2, true)
			check.equal(k[1], "hall")
			check.equal(k[2], "kitchen")
		end)

		test.case(
			"a house of rooms is furnished room by room: each passes the check, nothing crosses a wall",
			function()
				local houses, roomsSeen, kindsSeen = 0, 0, {}
				for _, size in { { 34, 38 }, { 40, 30 }, { 28, 44 }, { 46, 46 } } do
					for _, floors in { 2, 3 } do
						for seed = 1, 4 do
							local h = house({ size = size, floors = floors, name = `H{seed}` })
							h.rooms = { seed = seed }
							local parts, errs, extras = compile({ { building = h } })
							check.equal(#errs, 0, table.concat(errs, " | "))
							houses += 1
							local furnished = extras.rooms
							check.truthy(#furnished >= floors, `{#furnished} rooms furnished in {floors} floors`)
							-- every piece of furniture lies inside ONE furnished room's rect on its floor
							for _, p in parts do
								if FURNITURE[p.name] then
									local inOne = 0
									for _, r in furnished do
										local x0, z0, x1, z1 = r.rect[1], r.rect[2], r.rect[3], r.rect[4]
										if
											p.pos[1] - p.size[1] / 2 >= x0 - 1e-6
											and p.pos[1] + p.size[1] / 2 <= x1 + 1e-6
											and p.pos[3] - p.size[3] / 2 >= z0 - 1e-6
											and p.pos[3] + p.size[3] / 2 <= z1 + 1e-6
										then
											inOne += 1
										end
									end
									-- (rooms on different floors share a plan: the floor's own count is what matters)
									check.truthy(inOne >= 1, `{p.name} at {p.pos[1]}, {p.pos[3]} lies in no room`)
								end
							end
							for _, r in furnished do
								roomsSeen += 1
								kindsSeen[r.kind] = true
								-- (a stair's room may be left clear: a passage; every other room holds something standing)
								check.truthy(
									r.standing >= 1 or r.kind == "stair_shaft" or r.kind == "landing",
									`a {r.kind} with no furniture`
								)
							end
						end
					end
				end
				check.truthy(houses == 32 and roomsSeen > 64, `{houses} houses, {roomsSeen} rooms`)
				for _, k in { "hall", "kitchen", "chamber", "sanctum", "stair_shaft", "landing" } do
					check.truthy(kindsSeen[k], `no {k} in any house`)
				end
			end
		)

		test.case("no piece stands in a doorway's way in (the compiler's own claims of the room doors)", function()
			local checked = 0
			for seed = 1, 6 do
				local h = house({ size = { 40, 40 }, floors = 2, name = `D{seed}` })
				h.rooms = { seed = seed }
				local parts, errs, extras = compile({ { building = h } })
				check.equal(#errs, 0, table.concat(errs, " | "))
				for _, fit in extras.fits do
					if fit.kind == "opening" and string.find(fit.name, "room door", 1, true) then
						-- the doorway's way in: 7 studs either side of the wall, a stud past each jamb
						local along = fit.size[1] / 2 + 1
						for _, p in parts do
							if
								FURNITURE[p.name]
								and p.name ~= "Rug"
								and math.abs(p.pos[2] - p.size[2] / 2 - fit.pos[2]) < 1.5
							then
								local dx, dz = math.abs(p.pos[1] - fit.pos[1]), math.abs(p.pos[3] - fit.pos[3])
								local hx, hz = p.size[1] / 2, p.size[3] / 2
								-- (the wall runs along x or z: try both; a piece in the way overlaps either box)
								local inX = dx < along + hx - 1e-6 and dz < 7 + hz - 1e-6
								local inZ = dz < along + hz - 1e-6 and dx < 7 + hx - 1e-6
								-- (which way the wall runs: the doorway's middle lies on a furnished room's north or south edge)
								local wallAlongX = false
								for _, r in extras.rooms do
									if
										math.abs(r.y - fit.pos[2]) < 1 -- (a room of the door's own floor)
										and (math.abs(fit.pos[3] - r.rect[2]) < 0.35 or math.abs(fit.pos[3] - r.rect[4]) < 0.35)
										and fit.pos[1] > r.rect[1]
										and fit.pos[1] < r.rect[3]
									then
										wallAlongX = true
									end
								end
								local blocked = if wallAlongX then inX else inZ
								check.truthy(not blocked, `{p.name} at {p.pos[1]}, {p.pos[3]} in the way of {fit.name}`)
								checked += 1
							end
						end
					end
				end
			end
			check.truthy(checked > 50, `{checked} piece-door pairs looked at`)
		end)

		test.case('"interior": true with rooms still leaves the furniture out and says so', function()
			local h = house()
			h.interior = true
			local _, errs, extras, issues = compile({ { building = h } })
			check.equal(#errs, 0, table.concat(errs, " | "))
			check.equal(#extras.rooms, 0)
			local said = 0
			for _, i in issues do
				if i.severity == "warn" and string.find(i.message, '"byRoom": true', 1, true) then
					said += 1
				end
			end
			check.equal(said, 1)
		end)

		test.case("a room kind the floor names that does not exist is an error", function()
			local h = house()
			h.interior = { byRoom = true, rooms = { { "hall", "ballroom" } } }
			local _, errs = compile({ { building = h } })
			local found = false
			for _, e in errs do
				found = found or string.find(e, 'no room kind "ballroom"', 1, true) ~= nil
			end
			check.truthy(found, table.concat(errs, " | "))
		end)
	end)
end
