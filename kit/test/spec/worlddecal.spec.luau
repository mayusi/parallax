-- worlddecal.spec.luau (kit) — DECALS LAID ON A WORLD'S WALLS AND FLOORS (kit/lib/worlddecal.luau, the "decal" build
-- step; the owner's method list: "Decal-based detailing"). The pictures are made by kit/world/decals.py (tested in
-- test_world_decals.py). Here: what a step may say, where its decals lie, that none lies over another or on nothing,
-- and what reaches the game - with what is known of each decal given by hand (no files read).
-- Not claimed here: how a decal looks on a wall in the game. That needs its picture uploaded.
local frk = require("../frk")
local test, check = frk.test, frk.check

local Decal = require("../../lib/worlddecal")
local World = require("../../lib/world")

local PALETTE = {
	stone = { material = "Slate", color = { 90, 88, 86 } },
	clear = { material = "Glass", color = { 200, 200, 200 }, transparency = 1 },
}
-- a wall 40 long (x -20..20), 12 high (y 0..12), 2 thick (z 0..2): its north face is the plane z = 0
local WALL = { part = { name = "Wall", mat = "stone", size = { 40, 12, 2 }, pos = { 0, 6, 1 } } }
local FLOOR = { part = { name = "Floor", mat = "stone", size = { 40, 1, 40 }, pos = { 0, -0.5, -20 } } }

local function known(table_: { [string]: any }): (string) -> (any?, string?)
	return function(name: string)
		local k = table_[name]
		if k == nil then
			return nil, nil
		end
		return k.record, k.id
	end
end
local MADE = {
	Leak = { record = { name = "Leak", kind = "leak", tint = { 46, 40, 33 } }, id = "rbxassetid://501" },
	Moss = { record = { name = "Moss", kind = "moss" }, id = "rbxassetid://502" },
	Wet = { record = { name = "Wet", kind = "stain" } }, -- (made, not uploaded)
	Torn = { record = false }, -- (its record cannot be read)
}

local function compile(steps: { any }, decals: any?): (any, { any }, { string }, { string }, any)
	local model, parts, issues, extras = World.compile(
		{ name = "T", palette = PALETTE, build = steps },
		{ meshes = {}, decals = known(decals or MADE) }
	)
	local errors, warns = {}, {}
	for _, i in issues do
		if i.path ~= "spawn" then -- (these worlds have no spawn: not what is tested here)
			table.insert(if i.severity == "error" then errors else warns, i.message)
		end
	end
	return model, parts, errors, warns, extras
end

local function decalParts(parts: { any }): { any }
	local out = {}
	for _, p in parts do
		if string.sub(p.name, 1, 6) == "Decal_" then
			table.insert(out, p)
		end
	end
	return out
end

-- the Decal instance under a part in the Rojo model
local function inModel(node: any, found: { any })
	for _, child in node.Children or {} do
		if child.ClassName == "Decal" then
			table.insert(found, { decal = child, part = node })
		end
		inModel(child, found)
	end
end

return function()
	test.suite("Decals laid on a world's walls and floors", function()
		test.case(
			"one decal on a wall: a thin unseen part just off the face, the picture on its outward side",
			function()
				local model, parts, errors, warns, extras = compile({
					WALL,
					{ decal = { name = "Leak", at = { 5, 8, 0 }, size = { 3, 6 }, facing = "north" } },
				})
				check.equal(#errors, 0, table.concat(errors, " | "))
				check.equal(#warns, 0, table.concat(warns, " | "))
				local d = decalParts(parts)
				check.equal(#d, 1)
				local p = d[1]
				check.equal(p.name, "Decal_Leak")
				check.equal(`{p.size[1]} {p.size[2]} {p.size[3]}`, "3 6 0.05")
				check.equal(p.pos[1], 5)
				check.equal(p.pos[2], 8)
				check.truthy(math.abs(p.pos[3] - -0.055) < 1e-9) -- (0.03 off the face, and half its own thickness)
				check.equal(p.transparency, 1)
				check.equal(p.collide, false)
				check.equal(p.query, false)
				check.equal(p.castShadow, false)
				local found = {}
				inModel(model, found)
				check.equal(#found, 1)
				local props = found[1].decal.Properties
				check.equal(props.Texture, "rbxassetid://501")
				check.equal(props.Face, "Front") -- (a part's front looks toward -Z: north)
				check.equal(props.Transparency, 0)
				check.equal(props.Color3, nil)
				check.equal(found[1].part.Properties.CastShadow, false)
				check.equal(found[1].part.Properties.CanCollide, false)
				check.equal(found[1].part.Properties.Transparency, 1)
				check.equal(extras.decals[1].laid, 1)
				check.equal(extras.decals[1].placed, 1)
				-- the wall itself is as it was: it throws its shadow
				check.equal(parts[1].castShadow, nil)
			end
		)

		test.case("each side a face can look toward", function()
			-- a block 10 x 10 x 10 at the origin's top: faces at x = +-5, z = +-5, y = 10 and y = 0
			local block = { part = { name = "Block", mat = "stone", size = { 10, 10, 10 }, pos = { 0, 5, 0 } } }
			local cases = {
				{ "north", { 0, 5, -5 }, "Front", { 4, 2, 0.05 }, { 0, 5, -5.055 } },
				{ "south", { 0, 5, 5 }, "Back", { 4, 2, 0.05 }, { 0, 5, 5.055 } },
				{ "east", { 5, 5, 0 }, "Right", { 0.05, 2, 4 }, { 5.055, 5, 0 } },
				{ "west", { -5, 5, 0 }, "Left", { 0.05, 2, 4 }, { -5.055, 5, 0 } },
				{ "up", { 0, 10, 0 }, "Top", { 4, 0.05, 2 }, { 0, 10.055, 0 } },
				{ "down", { 0, 0, 0 }, "Bottom", { 4, 0.05, 2 }, { 0, -0.055, 0 } },
			}
			for _, c in cases :: { any } do
				local model, parts, errors = compile({
					block,
					{
						decal = {
							name = "Moss",
							at = c[2],
							size = { 4, 2 },
							facing = c[1],
							transparency = 0.25,
							tint = { 255, 128, 0 },
						},
					},
				})
				check.equal(#errors, 0, c[1] .. ": " .. table.concat(errors, " | "))
				local p = decalParts(parts)[1]
				for a = 1, 3 do
					check.truthy(math.abs(p.size[a] - c[4][a]) < 1e-9, `{c[1]} size {a}`)
					check.truthy(math.abs(p.pos[a] - c[5][a]) < 1e-9, `{c[1]} pos {a}`)
				end
				local found = {}
				inModel(model, found)
				check.equal(found[1].decal.Properties.Face, c[3])
				check.equal(found[1].decal.Properties.Transparency, 0.25)
				check.equal(found[1].decal.Properties.Color3.Color3[1], 1)
				check.truthy(math.abs(found[1].decal.Properties.Color3.Color3[2] - 128 / 255) < 1e-9)
				check.equal(found[1].decal.Properties.Color3.Color3[3], 0)
				-- the same decal a face further out, or looking the other way, lies on nothing
				local off = { c[2][1] * 1.2 + 0.4, c[2][2] + 0.4, c[2][3] * 1.2 + 0.4 }
				local _, _, away =
					compile({ block, { decal = { name = "Moss", at = off, size = { 4, 2 }, facing = c[1] } } })
				check.equal(#away, 1, c[1])
				check.truthy(string.find(away[1], "lies on nothing", 1, true))
			end
		end)

		test.case("many along a wall: side by side, none over another, each on the wall", function()
			local step = {
				decal = {
					names = { "Leak", "Moss" },
					along = { from = { -18, 0 }, to = { 18, 0 } },
					y = { 2, 11 },
					count = 8,
					size = { 2, 4 },
					facing = "north",
					seed = 5,
				},
			}
			local _, parts, errors, warns, extras = compile({ WALL, step })
			check.equal(#errors, 0, table.concat(errors, " | "))
			check.equal(#warns, 0)
			local d = decalParts(parts)
			check.equal(#d, 8)
			check.equal(extras.decals[1].laid, 8)
			check.equal(extras.decals[1].placed, 8)
			table.sort(d, function(a, b)
				return a.pos[1] < b.pos[1]
			end)
			local names: { [string]: number } = {}
			for i, p in d do
				names[p.name] = (names[p.name] or 0) + 1
				check.truthy(p.size[1] >= 2 and p.size[1] <= 4, "its side is in the range asked")
				check.equal(p.size[1], p.size[2])
				check.truthy(
					p.pos[1] - p.size[1] / 2 >= -18 - 1e-9 and p.pos[1] + p.size[1] / 2 <= 18 + 1e-9,
					"on the wall's length"
				)
				check.truthy(
					p.pos[2] - p.size[2] / 2 >= 2 - 1e-9 and p.pos[2] + p.size[2] / 2 <= 11 + 1e-9,
					"in the wall's height"
				)
				if i > 1 then
					local q = d[i - 1]
					check.truthy(q.pos[1] + q.size[1] / 2 <= p.pos[1] - p.size[1] / 2 + 1e-9, "no decal over another")
				end
			end
			check.truthy((names.Decal_Leak or 0) >= 1 and (names.Decal_Moss or 0) >= 1, "both names are used")
			-- the same seed lays the same; another seed another
			local _, again = compile({ WALL, step })
			local other = table.clone(step.decal) :: any
			other.seed = 6
			local _, moved = compile({ WALL, { decal = other } })
			local same, differs = true, false
			local a, b = decalParts(again), decalParts(moved)
			table.sort(a, function(x, y)
				return x.pos[1] < y.pos[1]
			end)
			table.sort(b, function(x, y)
				return x.pos[1] < y.pos[1]
			end)
			for i = 1, 8 do
				same = same and a[i].pos[1] == d[i].pos[1] and a[i].pos[2] == d[i].pos[2] and a[i].name == d[i].name
				differs = differs or b[i].pos[1] ~= d[i].pos[1]
			end
			check.truthy(same)
			check.truthy(differs)
			-- a wall facing east runs north-south
			local east = { part = { name = "E", mat = "stone", size = { 2, 12, 40 }, pos = { -1, 6, 0 } } }
			local _, eparts, eerr = compile({
				east,
				{
					decal = {
						names = { "Leak" },
						along = { from = { 0, -18 }, to = { 0, 18 } },
						y = { 1, 11 },
						count = 5,
						size = { 2, 3 },
						facing = "east",
					},
				},
			})
			check.equal(#eerr, 0, table.concat(eerr, " | "))
			check.equal(#decalParts(eparts), 5)
			for _, p in decalParts(eparts) do
				check.truthy(math.abs(p.pos[1] - 0.055) < 1e-9)
				check.equal(p.size[1], 0.05)
			end
		end)

		test.case("made, never made, not uploaded, lying on nothing", function()
			-- not uploaded: said once, left out, nothing half
			local model, parts, errors, warns, extras = compile({
				WALL,
				{ decal = { name = "Wet", at = { 0, 6, 0 }, size = { 3, 3 }, facing = "north" } },
				{ decal = { name = "Wet", at = { 8, 6, 0 }, size = { 3, 3 }, facing = "north" } },
			})
			check.equal(#errors, 0, table.concat(errors, " | "))
			check.equal(#warns, 1)
			check.truthy(string.find(warns[1], 'the decal "Wet" is not uploaded', 1, true))
			check.truthy(string.find(warns[1], "decals.Wet", 1, true))
			check.equal(#decalParts(parts), 0)
			local found = {}
			inModel(model, found)
			check.equal(#found, 0)
			check.equal(extras.decals[1].waiting, 1)
			check.equal(extras.decals[1].placed, 0)
			-- never made, and a record that cannot be read: errors that say how to make it
			local _, _, none =
				compile({ WALL, { decal = { name = "Ghost", at = { 0, 6, 0 }, size = { 3, 3 }, facing = "north" } } })
			check.equal(#none, 1)
			check.truthy(string.find(none[1], 'no decal "Ghost" - make it: lune run kit world decal Ghost', 1, true))
			local _, _, torn =
				compile({ WALL, { decal = { name = "Torn", at = { 0, 6, 0 }, size = { 3, 3 }, facing = "north" } } })
			check.equal(#torn, 1)
			check.truthy(string.find(torn[1], "no record that can be read", 1, true))
			-- on nothing: no wall yet (the decal before its wall), the wall's other side, in the air, inside the wall
			for _, steps in
				{
					{ { decal = { name = "Leak", at = { 0, 6, 0 }, size = { 3, 3 }, facing = "north" } }, WALL },
					{ WALL, { decal = { name = "Leak", at = { 0, 6, 0 }, size = { 3, 3 }, facing = "south" } } },
					{ WALL, { decal = { name = "Leak", at = { 0, 6, -3 }, size = { 3, 3 }, facing = "north" } } },
					{ WALL, { decal = { name = "Leak", at = { 0, 6, 1 }, size = { 3, 3 }, facing = "north" } } },
					{ WALL, { decal = { name = "Leak", at = { 0, 20, 0 }, size = { 3, 3 }, facing = "north" } } },
					{ WALL, { decal = { name = "Wet", at = { 0, 20, 0 }, size = { 3, 3 }, facing = "north" } } },
				} :: { any }
			do
				local _, p, bad = compile(steps)
				check.equal(#bad, 1, table.concat(bad, " | "))
				check.truthy(string.find(bad[1], "a decal lies on nothing", 1, true))
				check.equal(#decalParts(p), 0)
			end
			-- an unseen part and one nobody can touch are nothing to lie on
			local glass =
				{ part = { name = "Ghost", mat = "stone", size = { 40, 12, 2 }, pos = { 0, 6, 1 }, collide = false } }
			local _, _, onGhost =
				compile({ glass, { decal = { name = "Leak", at = { 0, 6, 0 }, size = { 3, 3 }, facing = "north" } } })
			check.equal(#onGhost, 1)
			-- a floor's stain lies on the floor part
			local _, fparts, ferr =
				compile({ FLOOR, { decal = { name = "Moss", at = { 3, 0, -10 }, size = { 5, 5 }, facing = "up" } } })
			check.equal(#ferr, 0, table.concat(ferr, " | "))
			check.equal(#decalParts(fparts), 1)
			-- many on a wall too short in height for them: each one on nothing is counted, three are named
			local _, _, many = compile({
				WALL,
				{
					decal = {
						names = { "Leak" },
						along = { from = { -18, 0 }, to = { 18, 0 } },
						y = { 14, 30 },
						count = 6,
						size = { 2, 3 },
						facing = "north",
					},
				},
			})
			check.equal(#many, 4)
			check.truthy(string.find(many[4], "6 decals of this step lie on nothing", 1, true))
		end)

		test.case("what a fresh reader got past the first rules", function()
			local leak = { name = "Leak", at = { 0, 6, 0 }, size = { 3, 3 }, facing = "north" }
			local function errorsOf(steps: { any }, decals: any?): { string }
				local _, _, bad = compile(steps, decals)
				return bad
			end
			local function said(steps: { any }, text: string, decals: any?)
				local bad = errorsOf(steps, decals)
				check.truthy(#bad >= 1, text)
				check.truthy(
					string.find(table.concat(bad, " | "), text, 1, true),
					text .. " <- " .. table.concat(bad, " | ")
				)
			end
			-- a wall turned 45 degrees is no face for a decal: its box in the air is not the wall
			local turned =
				{ part = { name = "Wall", mat = "stone", size = { 40, 12, 2 }, pos = { 0, 6, 1 }, rot = { 0, 45, 0 } } }
			said(
				{ turned, { decal = { name = "Leak", at = { 3.5, 6, -4.243 }, size = { 3, 3 }, facing = "north" } } },
				"lies on nothing"
			)
			-- a ball: the corner of its box is air
			local ball =
				{ part = { name = "Ball", mat = "stone", size = { 10, 10, 10 }, pos = { 0, 5, 0 }, shape = "Ball" } }
			said(
				{ ball, { decal = { name = "Leak", at = { 4, 9, -5 }, size = { 1, 1 }, facing = "north" } } },
				"lies on nothing"
			)
			said(
				{ ball, { decal = { name = "Leak", at = { 0, 5, -5 }, size = { 1, 1 }, facing = "north" } } },
				"lies on nothing"
			)
			-- a wall turned a quarter still stands square: its long side now faces east and west
			local quarter =
				{ part = { name = "Wall", mat = "stone", size = { 40, 12, 2 }, pos = { 1, 6, 0 }, rot = { 0, 90, 0 } } }
			check.equal(
				#errorsOf({ quarter, { decal = { name = "Leak", at = { 0, 6, 5 }, size = { 3, 3 }, facing = "west" } } }),
				0
			)
			-- the WHOLE decal is on the face: off the wall's end, over its top
			said(
				{ WALL, { decal = { name = "Leak", at = { 19.5, 6, 0 }, size = { 3, 3 }, facing = "north" } } },
				"it hangs 1 studs off the face"
			)
			said(
				{ WALL, { decal = { name = "Leak", at = { 0, 6, 0 }, size = { 3, 64 }, facing = "north" } } },
				"it hangs 26 studs off the face"
			)
			said(
				{ WALL, { decal = { name = "Leak", at = { 0, 6, 0 }, size = { 41, 3 }, facing = "north" } } },
				"the decal 41 x 3"
			)
			check.equal(#errorsOf({
				WALL,
				{ decal = { name = "Leak", at = { 18.5, 6, 0 }, size = { 3, 12 }, facing = "north" } },
			}), 0) -- (it just fits)
			-- many along a wall whose "y" says more height than the wall has: none may stand over the wall's top
			local tall = {
				decal = {
					names = { "Leak" },
					along = { from = { -18, 0 }, to = { 18, 0 } },
					y = { 0, 30 },
					count = 6,
					size = { 2, 4 },
					facing = "north",
					seed = 2,
				},
			}
			local _, tparts, terr = compile({ WALL, tall })
			check.truthy(#terr >= 1)
			check.equal(#decalParts(tparts), 0 + (function()
				local n = 0
				for _, p in decalParts(tparts) do
					check.truthy(p.pos[2] + p.size[2] / 2 <= 12.05, "no decal over the wall's top")
					n += 1
				end
				return n
			end)())
			-- a thin thing is a face too (a slab 0.2 thick), from above
			local slab = { part = { name = "Slab", mat = "stone", size = { 10, 0.2, 10 }, pos = { 0, 5.1, 0 } } }
			check.equal(
				#errorsOf({ slab, { decal = { name = "Moss", at = { 0, 5.2, 0 }, size = { 4, 4 }, facing = "up" } } }),
				0
			)
			-- an unseen wall is none
			local unseen = { part = { name = "Unseen", mat = "clear", size = { 40, 12, 2 }, pos = { 0, 6, 1 } } }
			said({ unseen, { decal = leak } }, "lies on nothing")
			-- a face another part stands over: a crate against the wall
			local crate = { part = { name = "Crate", mat = "stone", size = { 4, 4, 4 }, pos = { 0, 6, -2 } } }
			said({ WALL, crate, { decal = leak } }, "another part stands over that spot")
			check.equal(#errorsOf({
				WALL,
				crate,
				{ decal = { name = "Leak", at = { 8, 6, 0 }, size = { 3, 3 }, facing = "north" } },
			}), 0)
			-- two decals on one spot
			said({
				WALL,
				{ decal = leak },
				{ decal = { name = "Moss", at = { 0, 6, 0 }, size = { 2, 2 }, facing = "north" } },
			}, "two decals lie on one spot")
			-- blood by the step's tint, and by the picture's own tint under the step's
			said({
				WALL,
				{
					decal = {
						name = "Leak",
						at = { 0, 6, 0 },
						size = { 3, 3 },
						facing = "north",
						tint = { 255, 0, 0 },
					},
				},
			}, "reads as blood")
			local pale = {
				Pale = { record = { name = "Pale", kind = "stain", tint = { 255, 120, 120 } }, id = "rbxassetid://9" },
			}
			said({
				WALL,
				{
					decal = {
						name = "Pale",
						at = { 0, 6, 0 },
						size = { 3, 3 },
						facing = "north",
						tint = { 200, 200, 200 },
					},
				},
			}, 'the decal "Pale" under this "tint" reads as blood', pale)
			check.equal(#errorsOf({
				WALL,
				{
					decal = {
						name = "Leak",
						at = { 0, 6, 0 },
						size = { 3, 3 },
						facing = "north",
						tint = { 200, 200, 200 },
					},
				},
			}), 0)
		end)

		test.case("what a step may not say", function()
			local good = { name = "Leak", at = { 0, 6, 0 }, size = { 3, 3 }, facing = "north" }
			check.equal(#Decal.problems(good), 0)
			local function one(change: { [string]: any }, text: string)
				local spec = table.clone(good) :: any
				for k, v in change do
					spec[k] = if v == "none" then nil else v
				end
				local said = Decal.problems(spec)
				check.truthy(#said >= 1, text)
				check.truthy(
					string.find(table.concat(said, " | "), text, 1, true),
					text .. " <- " .. table.concat(said, " | ")
				)
			end
			one({ name = "a b" }, '"name" is the decal made by')
			one({ name = "../x" }, '"name" is the decal made by')
			one({ name = 5 }, '"name" is the decal made by')
			one({ at = { 0, 6 } }, '"at" is [x, y, z]')
			one({ at = { 0, 0 / 0, 0 } }, '"at" is [x, y, z]')
			one({ size = { 3 } }, '"size" is [width, height]')
			one({ size = { 0.4, 3 } }, '"size" is [width, height]')
			one({ size = { 3, 65 } }, '"size" is [width, height]')
			one({ facing = "left" }, '"facing" is the side')
			one({ facing = "none" }, '"facing" is the side')
			one({ transparency = 1 }, '"transparency" is 0')
			one({ transparency = -0.1 }, '"transparency" is 0')
			one({ tint = { 255, 0 } }, '"tint" is [r, g, b]')
			one({ tint = { 256, 0, 0 } }, '"tint" is [r, g, b]')
			one({ tint = { 255, 0, 0 } }, "reads as blood")
			one({ tint = { 120, 54, 54 } }, "reads as blood")
			one({ seed = 3 }, 'one decal has no "seed"')
			one({ turn = 90 }, '"turn" is not a word it knows')
			one({ ground = true }, '"ground" is not a word it knows')
			check.equal(#Decal.problems(nil), 1)
			check.equal(#Decal.problems("Leak"), 1)
			-- the ends of the ranges are in
			for _, ok in
				{ { size = { 0.5, 64 } }, { transparency = 0 }, { transparency = 0.99 }, { tint = { 0, 255, 0 } } } :: { any }
			do
				local spec = table.clone(good) :: any
				for k, v in ok do
					spec[k] = v
				end
				check.equal(#Decal.problems(spec), 0)
			end
			local many = {
				names = { "Leak" },
				along = { from = { -18, 0 }, to = { 18, 0 } },
				y = { 2, 11 },
				count = 8,
				size = { 2, 4 },
				facing = "north",
			}
			check.equal(#Decal.problems(many), 0)
			local function more(change: { [string]: any }, text: string)
				local spec = table.clone(many) :: any
				for k, v in change do
					spec[k] = if v == "none" then nil else v
				end
				local said = Decal.problems(spec)
				check.truthy(
					string.find(table.concat(said, " | "), text, 1, true),
					text .. " <- " .. table.concat(said, " | ")
				)
			end
			more({ name = "Leak" }, "either one")
			more({ at = { 0, 0, 0 } }, "either one")
			more({ names = {} }, '"names" is 1 to 16')
			more({ names = { "a b" } }, '"names" is 1 to 16')
			more({ names = "none" }, '"names" is 1 to 16')
			more({ along = { from = { 0, 0 } } }, '"along" is {')
			more({ along = { from = { -18, 0 }, to = { 18, 4 } } }, "runs east-west")
			more({ facing = "east" }, "runs north-south")
			more({ along = { from = { 0, 0 }, to = { 0.5, 0 } } }, "has no length")
			more({ facing = "up" }, "along a WALL")
			more({ y = { 11, 2 } }, '"y" is [lowest, highest]')
			more({ y = { 5 } }, '"y" is [lowest, highest]')
			more({ count = 0 }, '"count" is a whole number')
			more({ count = 2.5 }, '"count" is a whole number')
			more({ count = 201 }, '"count" is a whole number')
			more({ size = { 4, 2 } }, "[smallest, largest]")
			more({ size = { 0.4, 2 } }, "[smallest, largest]")
			more({ seed = -1 }, '"seed" is a whole number')
			more({ seed = 70000 }, '"seed" is a whole number')
			more({ count = 19 }, "do not stand side by side") -- (36 studs / 19 < 2)
			more({ y = { 2, 3.5 } }, "the smallest decal is 2")
			check.equal(#Decal.problems((function()
				local s = table.clone(many) :: any
				s.count = 18 -- (36 studs / 18 = 2: they just fit)
				return s
			end)()), 0)
		end)

		test.case("an id is a whole number over 0 and nothing else", function()
			check.equal(Decal.id(501), "rbxassetid://501")
			check.equal(Decal.id("502"), "rbxassetid://502")
			check.equal(Decal.id("rbxassetid://503"), "rbxassetid://503")
			for _, v in { 0, -5, 1.5, "0", "abc", "id 5", "rbxassetid://", "http://x/5", {}, true, 2 ^ 60 } :: { any } do
				check.equal(Decal.id(v), nil)
			end
			check.equal(Decal.id(nil), nil)
			-- the land holds a floor's decal (within a stud), never a wall's
			local function at(facing: string, y: number): any
				return { name = "Moss", at = { 0, y, 0 }, size = { 2, 2 }, facing = facing }
			end
			check.equal(Decal.lies(at("up", 5), {}, 5), nil)
			check.equal(Decal.lies(at("up", 5.2), {}, 5), nil)
			check.truthy(Decal.lies(at("up", 5.3), {}, 5) ~= nil) -- (over a quarter stud up: it floats)
			check.truthy(Decal.lies(at("up", 4.7), {}, 5) ~= nil)
			check.truthy(Decal.lies(at("up", 5), {}, nil) ~= nil)
			check.truthy(Decal.lies(at("north", 5), {}, 5) ~= nil)
			check.truthy(Decal.lies(at("down", 5), {}, 5) ~= nil)
			-- what reads as blood: ONE TABLE, held in kit/test/python/test_world_decals.py too
			for _, c in
				{
					{ 150, 20, 20 },
					{ 120, 10, 40 },
					{ 200, 80, 80 },
					{ 61, 0, 0 },
					{ 255, 114, 114 },
					{ 120, 54, 54 },
					{ 59, 0, 0 },
					{ 80, 0, 40 },
					{ 130, 20, 60 },
					{ 100, 40, 60 },
					{ 40, 0, 0 },
					{ 200, 40, 95 },
					{ 150, 60, 50 },
					{ 255, 0, 0 },
					{ 30, 0, 0 },
					{ 200, 50, 20 },
					{ 200, 20, 120 },
				}
			do
				check.equal(Decal.bloody(c[1], c[2], c[3]), true, `{c[1]} {c[2]} {c[3]}`)
			end
			for _, c in
				{
					{ 150, 75, 40 },
					{ 140, 60, 30 },
					{ 46, 40, 33 },
					{ 66, 56, 42 },
					{ 22, 21, 20 },
					{ 58, 84, 40 },
					{ 16, 15, 15 },
					{ 200, 95, 40 },
					{ 29, 0, 0 },
					{ 120, 90, 80 },
					{ 0, 0, 0 },
					{ 60, 60, 200 },
					{ 200, 100, 200 },
					{ 255, 255, 255 },
					{ 200, 60, 20 },
					{ 200, 20, 130 },
					{ 100, 100, 20 },
				}
			do
				check.equal(Decal.bloody(c[1], c[2], c[3]), false, `{c[1]} {c[2]} {c[3]}`)
			end
			-- the sides a face can look toward are Roblox's six, each once
			local faces = {}
			for side, f in Decal.FACING do
				faces[f.face] = side
				check.equal(f.normal[1] ^ 2 + f.normal[2] ^ 2 + f.normal[3] ^ 2, 1)
			end
			check.equal(faces.Front, "north")
			check.equal(faces.Back, "south")
			check.equal(faces.Right, "east")
			check.equal(faces.Left, "west")
			check.equal(faces.Top, "up")
			check.equal(faces.Bottom, "down")
		end)
	end)
end
