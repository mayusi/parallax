-- worldon.spec.luau (kit) — THINGS SET DOWN ON A MESH'S SURFACE (a mesh step's "on"; the owner's method list:
-- "Geometry Nodes scattering", "Surface-based scattering"). The points are made in Blender (kit world scatter-on:
-- kit/world/gnscatter_blender.py, its words tested in test_world_gnscatter.py). Here the compiler is held to what
-- it does with them: each piece's foot on its point, its up along the surface's normal, scaled and turned with
-- the mesh - on points made by hand for a box.
-- Not claimed here: that the scatter looks right. That is a built world, looked at.
local frk = require("../frk")
local test, check = frk.test, frk.check

local World = require("../../lib/world")

local PALETTE = {
	rock = { material = "Slate", color = { 70, 68, 66 } },
	moss = { material = "Grass", color = { 70, 110, 50 } },
}

-- a box 20 x 10 x 8 studs standing on its base (x -10..10, y 0..10, z -4..4), 12 triangles
local REG = { crag = { kind = "rock", size = { 20, 10, 8 }, min = { -10, 0, -4 }, tris = 12, textured = false } }
local POINTS = {
	tris = 12,
	min = { -10, 0, -4 },
	size = { 20, 10, 8 },
	gap = 3,
	points = {
		{ pos = { 0, 10, 0 }, normal = { 0, 1, 0 } }, -- on its top
		{ pos = { 10, 5, 0 }, normal = { 1, 0, 0 } }, -- on its east face
		{ pos = { -4, 0, 2 }, normal = { 0, -1, 0 } }, -- under it
		{ pos = { 3, 6, 4 }, normal = { 0, 0, 2 } }, -- on its south face (a normal that is not of length 1)
		{ pos = { 5, 10, -3 }, normal = { 0.6, 0.8, 0 } }, -- on a slope
	},
}

-- points as the command writes them for the crag: its triangles and its box with them
local function made(points: any, more: any?): any
	local d: any = { tris = 12, min = { -10, 0, -4 }, size = { 20, 10, 8 }, points = points }
	for k, v in more or {} do
		d[k] = if v == "none" then nil else v
	end
	return d
end

local function compile(mesh: any, scatters: any?): ({ any }, { string }, any)
	local _, parts, issues, extras = World.compile(
		{ name = "T", scale = "r6", palette = PALETTE, build = { { mesh = mesh } } },
		{ meshes = REG, scatters = scatters or { ["crag.moss"] = POINTS } }
	)
	local errors = {}
	for _, i in issues do
		if i.severity == "error" then
			table.insert(errors, i.message)
		end
	end
	return parts, errors, extras
end

local function step(more: any?, on: any?): any
	local s: any = {
		name = "Crag",
		mesh = "crag",
		mat = "rock",
		pos = { 0, 0, 0 },
		on = { points = "moss", part = { size = { 2, 0.5, 1 }, mat = "moss" }, turn = false },
	}
	for k, v in more or {} do
		s[k] = v
	end
	for k, v in on or {} do
		s.on[k] = v
	end
	return s
end

local function pieces(parts: { any }): { any }
	local out = {}
	for _, p in parts do
		if p.name == "On" then
			table.insert(out, p)
		end
	end
	return out
end

local function near(a: number, b: number): boolean
	return math.abs(a - b) < 1e-9
end

-- the piece's own up (the middle column of its turn), and whether its turn is a true one (three unit axes at
-- right angles, right-handed)
local function up(p: any): { number }
	return { p.rot[1][2], p.rot[2][2], p.rot[3][2] }
end
local function trueTurn(p: any): boolean
	local c = {}
	for col = 1, 3 do
		c[col] = { p.rot[1][col], p.rot[2][col], p.rot[3][col] }
	end
	local function dot(a: { number }, b: { number }): number
		return a[1] * b[1] + a[2] * b[2] + a[3] * b[3]
	end
	local cross = {
		c[1][2] * c[2][3] - c[1][3] * c[2][2],
		c[1][3] * c[2][1] - c[1][1] * c[2][3],
		c[1][1] * c[2][2] - c[1][2] * c[2][1],
	}
	return near(dot(c[1], c[1]), 1)
		and near(dot(c[2], c[2]), 1)
		and near(dot(c[3], c[3]), 1)
		and near(dot(c[1], c[2]), 0)
		and near(dot(c[1], c[3]), 0)
		and near(dot(c[2], c[3]), 0)
		and near(dot(cross, c[3]), 1)
end

return function()
	test.suite("Things set down on a mesh's surface", function()
		test.case("each piece stands on its point, its up along the surface's normal", function()
			local parts, errors, extras = compile(step())
			check.equal(#errors, 0, table.concat(errors, " | "))
			local on = pieces(parts)
			check.equal(#on, 5)
			-- on the top: its middle half its height over the point, upright
			check.truthy(near(on[1].pos[1], 0) and near(on[1].pos[2], 10.25) and near(on[1].pos[3], 0))
			check.truthy(near(up(on[1])[2], 1))
			-- on the east face: half its height out to the east, its up pointing east
			check.truthy(near(on[2].pos[1], 10.25) and near(on[2].pos[2], 5) and near(on[2].pos[3], 0))
			check.truthy(near(up(on[2])[1], 1) and near(up(on[2])[2], 0))
			-- under it: hanging down
			check.truthy(near(on[3].pos[1], -4) and near(on[3].pos[2], -0.25) and near(on[3].pos[3], 2))
			check.truthy(near(up(on[3])[2], -1))
			-- a normal of any length is a direction
			check.truthy(near(on[4].pos[3], 4.25) and near(up(on[4])[3], 1))
			-- on a slope: along the slope's normal
			check.truthy(near(on[5].pos[1], 5 + 0.6 * 0.25) and near(on[5].pos[2], 10 + 0.8 * 0.25))
			check.truthy(near(up(on[5])[1], 0.6) and near(up(on[5])[2], 0.8))
			for _, p in on do
				check.truthy(trueTurn(p))
				check.equal(`{p.size[1]} {p.size[2]} {p.size[3]}`, "2 0.5 1")
				check.equal(p.material, "Grass")
				check.equal(p.collide, false)
			end
			-- on a level or a leaning surface the piece's long side lies level (no chance turn asked)
			check.truthy(near(on[1].rot[2][1], 0) and near(on[2].rot[2][1], 0) and near(on[5].rot[2][1], 0))
			local m = extras.onMeshes[1]
			check.equal(m.name, "Crag")
			check.equal(m.mesh, "crag")
			check.equal(m.points, 5)
			check.equal(m.placed, 5)
			check.equal(m.gap, 3)
			-- the mesh itself is placed as before
			local meshes = 0
			for _, p in parts do
				meshes += if p.name == "KitMesh" then 1 else 0
			end
			check.equal(meshes, 1)
			check.equal(#parts, 6)
		end)

		test.case("the points are the mesh's: moved, scaled and turned with it", function()
			-- moved
			local moved = pieces((compile(step({ pos = { 100, 20, -30 } }))))
			check.truthy(near(moved[1].pos[1], 100) and near(moved[1].pos[2], 30.25) and near(moved[1].pos[3], -30))
			-- twice as tall: the points twice as far from its foot, the piece its own size, the gap twice as wide
			local parts, _, extras = compile(step({ height = 20 }))
			local tall = pieces(parts)
			check.truthy(near(tall[1].pos[2], 20.25))
			check.truthy(near(tall[2].pos[1], 20.25) and near(tall[2].pos[2], 10))
			check.equal(tall[1].size[1], 2)
			check.equal(extras.onMeshes[1].gap, 6)
			-- a quarter turn: the east face's piece goes where the mesh's east face went, and points that way
			local turned = pieces((compile(step({ yaw = 90 }))))
			local mesh
			for _, p in (compile(step({ yaw = 90 }))) do
				if p.name == "KitMesh" then
					mesh = p
				end
			end
			-- (the mesh's own turn carries its local +x to this world direction)
			local east = { mesh.rot[1][1], mesh.rot[2][1], mesh.rot[3][1] }
			check.truthy(math.abs(east[1]) < 1e-9 and near(math.abs(east[3]), 1))
			check.truthy(near(turned[2].pos[1], east[1] * 10.25) and near(turned[2].pos[3], east[3] * 10.25))
			check.truthy(near(up(turned[2])[1], east[1]) and near(up(turned[2])[3], east[3]))
			check.truthy(near(turned[1].pos[2], 10.25) and near(up(turned[1])[2], 1)) -- (the top stays the top)
			for _, p in turned do
				check.truthy(trueTurn(p))
			end
		end)

		test.case("sink, share, a chance turn, collide", function()
			-- sunk into the surface
			local sunk = pieces((compile(step(nil, { sink = 0.2 }))))
			check.truthy(near(sunk[1].pos[2], 10.05) and near(sunk[2].pos[1], 10.05))
			-- a chance turn about the normal: still upright on its point, its side way turned; by the seed
			local a = pieces((compile(step(nil, { turn = true, seed = 3 }))))
			local b = pieces((compile(step(nil, { turn = true, seed = 3 }))))
			local c = pieces((compile(step(nil, { turn = true, seed = 4 }))))
			local unsaid = step()
			unsaid.on.turn = nil
			local d = pieces((compile(unsaid))) -- (turned by chance unless it says false)
			local differs, turnedAtAll = 0, 0
			for i = 1, 5 do
				check.truthy(trueTurn(a[i]))
				check.truthy(near(up(a[i])[1], up(sunk[i])[1]) and near(up(a[i])[2], up(sunk[i])[2]))
				check.equal(a[i].rot[1][1], b[i].rot[1][1])
				differs += if near(a[i].rot[1][1], c[i].rot[1][1]) and near(a[i].rot[3][1], c[i].rot[3][1])
					then 0
					else 1
				turnedAtAll += if near(d[i].rot[1][1], sunk[i].rot[1][1])
						and near(d[i].rot[3][1], sunk[i].rot[3][1])
					then 0
					else 1
			end
			check.truthy(differs >= 4)
			check.truthy(turnedAtAll >= 4)
			-- a share of the points: fewer pieces, each where it stood with all of them; by the seed
			local many = made({})
			for i = 1, 200 do
				table.insert(many.points, { pos = { i / 10 - 10, 10, 0 }, normal = { 0, 1, 0 } })
			end
			local all = pieces((compile(step(), { ["crag.moss"] = many })))
			local half = pieces((compile(step(nil, { share = 0.5 }), { ["crag.moss"] = many })))
			check.equal(#all, 200)
			check.truthy(#half > 70 and #half < 130, `{#half} of 200`)
			local where: { [number]: boolean } = {}
			for _, p in all do
				where[math.floor(p.pos[1] * 10 + 0.5)] = true
			end
			for _, p in half do
				check.truthy(where[math.floor(p.pos[1] * 10 + 0.5)])
			end
			local other = pieces((compile(step(nil, { share = 0.5, seed = 9 }), { ["crag.moss"] = many })))
			local same = 0
			local firsts: { [number]: boolean } = {}
			for _, p in half do
				firsts[math.floor(p.pos[1] * 10 + 0.5)] = true
			end
			for _, p in other do
				same += if firsts[math.floor(p.pos[1] * 10 + 0.5)] then 1 else 0
			end
			check.truthy(same < #other)
			-- collide said
			check.equal(pieces((compile(step(nil, { collide = true }))))[1].collide, true)
		end)

		test.case("what cannot be set down is said", function()
			local function wrong(more: any, on: any, text: string, scatters: any?)
				local s = step(more, on)
				if on == false then
					s.on = 5
				end
				local parts, errors = compile(s, scatters)
				check.equal(#pieces(parts), 0)
				check.truthy(#errors >= 1)
				check.truthy(string.find(table.concat(errors, " | "), text, 1, true), table.concat(errors, " | "))
			end
			wrong(nil, false, [[a mesh's "on" is {]])
			wrong(
				nil,
				{ points = "lichen" },
				'no points "lichen" on the mesh "crag" - make them: lune run kit world scatter-on crag --as lichen'
			)
			wrong(nil, { points = 5 }, ".points is the name")
			wrong(nil, { part = { size = { 2, 0.5 }, mat = "moss" } }, ".part is")
			wrong(nil, { part = { size = { 2, 0.01, 1 }, mat = "moss" } }, ".part is")
			wrong(nil, { part = { size = { 2, 65, 1 }, mat = "moss" } }, ".part is")
			wrong(nil, { part = { size = { 2, 0.5, 1 } } }, ".part is")
			wrong(nil, { part = "moss" }, ".part is")
			wrong(nil, { sink = 0.6 }, ".sink is")
			wrong(nil, { sink = -0.1 }, ".sink is")
			wrong(nil, { share = 0 }, ".share is")
			wrong(nil, { share = 1.1 }, ".share is")
			wrong(nil, { seed = 1.5 }, ".seed is")
			wrong(nil, { turn = "yes" }, ".turn is true or false")
			wrong(nil, { collide = 1 }, ".collide is true or false")
			wrong(nil, { gap = 3 }, ".gap is not a word it knows")
			-- points made on another build of the mesh
			wrong(nil, nil, 'were made on another build of "crag" (they say 14 triangles', {
				["crag.moss"] = made(POINTS.points, { tris = 14 }),
			})
			-- ... the same count of triangles in another box (the mesh made larger); points that do not say their
			-- triangles or their box at all; a count that is no number
			wrong(nil, nil, "in a box of 40 x 10 x 8; the mesh has 12 in 20 x 10 x 8", {
				["crag.moss"] = made(POINTS.points, { size = { 40, 10, 8 } }),
			})
			wrong(
				nil,
				nil,
				"were made on another build",
				{ ["crag.moss"] = made(POINTS.points, { min = { -9, 0, -4 } }) }
			)
			wrong(nil, nil, "were made on another build", { ["crag.moss"] = made(POINTS.points, { tris = "none" }) })
			wrong(nil, nil, "in a box of no size", { ["crag.moss"] = made(POINTS.points, { size = "none" }) })
			wrong(nil, nil, "were made on another build", { ["crag.moss"] = made(POINTS.points, { tris = "12" }) })
			-- ... and a mesh whose registry has no count either: nothing to hold the points to, so they are refused
			local _, parts0, issues0 = World.compile(
				{ name = "T", scale = "r6", palette = PALETTE, build = { { mesh = step() } } },
				{
					meshes = { crag = { kind = "rock", size = { 20, 10, 8 }, min = { -10, 0, -4 }, textured = false } },
					scatters = { ["crag.moss"] = made(POINTS.points, { tris = "none" }) },
				}
			)
			check.equal(#pieces(parts0), 0)
			local said0 = {}
			for _, i in issues0 do
				table.insert(said0, i.message)
			end
			check.truthy(string.find(table.concat(said0, " | "), "were made on another build", 1, true))
			-- points that are no list; none at all; too many; one that is not on the mesh
			wrong(nil, nil, "are no list of points", { ["crag.moss"] = made({ a = POINTS.points[1] }) })
			wrong(nil, nil, "are no list of points", { ["crag.moss"] = made({}) })
			local over = {}
			for i = 1, 4001 do
				over[i] = { pos = { (i % 100) / 10 - 5, 10, 0 }, normal = { 0, 1, 0 } }
			end
			wrong(nil, nil, "4001 points: over 4000 pieces", { ["crag.moss"] = made(over) })
			wrong(nil, nil, 'point 2 of "moss" lies outside the mesh "crag"', {
				["crag.moss"] = made({ POINTS.points[1], { pos = { 1e9, 5, 0 }, normal = { 1, 0, 0 } } }),
			})
			wrong(nil, nil, "lies outside the mesh", {
				["crag.moss"] = made({ { pos = { 0, 10.6, 0 }, normal = { 0, 1, 0 } } }),
			})
			-- a piece's unknown words; a piece of stuff the palette does not have is said ONCE, not once a point
			wrong(
				nil,
				{ part = { size = { 2, 0.5, 1 }, mat = "moss", shape = "Ball" } },
				".part.shape is not a word a piece knows"
			)
			local _, errors = compile(step(nil, { part = { size = { 2, 0.5, 1 }, mat = "lichen" } }))
			check.equal(#errors, 1)
			-- an imported asset of several meshes takes no points
			local _, several = World.compile(
				{ name = "T", scale = "r6", palette = PALETTE, build = { { mesh = step({ mesh = "pile" }) } } },
				{
					meshes = {
						pile = {
							kind = "import",
							size = { 20, 10, 8 },
							min = { -10, 0, -4 },
							tris = 12,
							parts = { "pile_a" },
						},
						pile_a = { kind = "import", size = { 20, 10, 8 }, min = { -10, 0, -4 }, tris = 12 },
					},
					scatters = { ["pile.moss"] = POINTS },
				}
			)
			check.equal(#pieces(several), 0)
			-- a point that is no point
			wrong(nil, nil, "point 2 of", {
				["crag.moss"] = made({ POINTS.points[1], { pos = { 0, 0 }, normal = { 0, 1, 0 } } }),
			})
			wrong(nil, nil, "point 1 of", {
				["crag.moss"] = made({ { pos = { 0, 0, 0 }, normal = { 0, 0, 0 } } }),
			})
			-- "on": false and no "on": the mesh alone
			local plain = step()
			plain.on = false
			local parts, none, extras = compile(plain)
			check.equal(#none, 0)
			check.equal(#parts, 1)
			check.equal(#extras.onMeshes, 0)
		end)
	end)
end
