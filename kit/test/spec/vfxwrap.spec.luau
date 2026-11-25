-- vfxwrap.spec.luau (kit) - A MARK DRAPED OVER UNEVEN GROUND (the decal layer's "wrap"; the owner's method list:
-- projected textures). Roblox has no projector - a Decal sits on one face of one part - so the mark is a mesh sheet
-- whose points lie where rays find the ground. The rule that places the points (VfxStage `wrapPoints`) is run from the
-- runtime's own source against made ground; the wiring is read from the code. How it LOOKS is the engine's to show.
local frk = require("../frk")
local fs = require("@lune/fs")
local luau = require("@lune/luau")
local roblox = require("@lune/roblox")
local test, check = frk.test, frk.check

local Vector3: any, CFrame: any = (roblox :: any).Vector3, (roblox :: any).CFrame

local function rule(): any
	local text = fs.readFile("src/kit/VfxStage.luau")
	local a = string.find(text, "local WRAP_LIFT", 1, true)
	local b = string.find(text, "local function plainPart", 1, true)
	assert(a and b and b > a, "VfxStage has no wrapPoints rule")
	return luau.load(
		string.sub(text, a, b - 1) .. "\nreturn { wrapPoints = wrapPoints, wrapKey = wrapKey, lift = WRAP_LIFT }",
		{
			debugName = "wrapPoints",
			environment = { Vector3 = Vector3, CFrame = CFrame },
		}
	)()
end

local function code(path: string): string
	local out = {}
	for line in string.gmatch(fs.readFile(path), "[^\n]+") do
		local cut = string.find(line, "--", 1, true)
		table.insert(out, if cut then string.sub(line, 1, cut - 1) else line)
	end
	local flat = string.gsub(table.concat(out, " "), "%s+", " ")
	flat = string.gsub(flat, "%( ", "(")
	return (string.gsub(flat, ",? %)", ")"))
end

return function()
	test.suite("a mark draped over uneven ground (wrap)", function()
		local r = rule()
		local up = Vector3.new(0, 1, 0)
		local function near(a: any, b: any): boolean
			return (a - b).Magnitude < 1e-4
		end

		test.case("on flat ground the mark is the flat mark, lifted a little, row by row", function()
			local pts = r.wrapPoints(4, 8, 4, CFrame.new(10, 2, -5), function(q)
				return Vector3.new(q.X, 2, q.Z), up
			end)
			check.equal(#pts, 25)
			check.is_true(near(pts[1], Vector3.new(6, 2 + r.lift, -7))) -- the first corner: -w/2, -d/2
			check.is_true(near(pts[5], Vector3.new(14, 2 + r.lift, -7))) -- the end of the first row
			check.is_true(near(pts[25], Vector3.new(14, 2 + r.lift, -3))) -- the last corner
			check.is_true(near(pts[13], Vector3.new(10, 2 + r.lift, -5))) -- its middle
		end)
		test.case("on a slope every point lies ON the slope, off it along its normal", function()
			-- ground: y = 0.5 x (a ramp); its normal
			local n = Vector3.new(-0.5, 1, 0).Unit
			local pts = r.wrapPoints(6, 12, 12, CFrame.new(0, 0, 0), function(q)
				return Vector3.new(q.X, 0.5 * q.X, q.Z), n
			end)
			for _, p in pts do
				local onGround = p - n * r.lift
				check.is_true(math.abs(onGround.Y - 0.5 * onGround.X) < 1e-4)
			end
			check.is_true(pts[7].Y > pts[1].Y + 5) -- the far side of the mark is 6 studs up the ramp
		end)
		test.case("over a step the mark follows both levels; a flat Decal would float or be cut", function()
			local pts = r.wrapPoints(8, 16, 16, CFrame.new(0, 0, 0), function(q)
				return Vector3.new(q.X, if q.X > 0 then 3 else 0, q.Z), up
			end)
			local low, high = 0, 0
			for _, p in pts do
				if math.abs(p.Y - r.lift) < 1e-4 then
					low += 1
				elseif math.abs(p.Y - (3 + r.lift)) < 1e-4 then
					high += 1
				end
			end
			check.equal(low + high, 81)
			check.is_true(low > 30 and high > 30)
		end)
		test.case("a point that finds no ground lies on the mark's own plane", function()
			local pts = r.wrapPoints(4, 8, 8, CFrame.new(0, 5, 0), function(q)
				if q.X > 1 then
					return nil, nil -- a hole: nothing under this side
				end
				return Vector3.new(q.X, 1, q.Z), up
			end)
			check.is_true(near(pts[5], Vector3.new(4, 5 + r.lift, -4)))
			check.is_true(near(pts[1], Vector3.new(-4, 1 + r.lift, -4)))
		end)
		test.case("the mark turns with its frame: the rays start on the mark's own plane", function()
			local asked = {}
			r.wrapPoints(2, 4, 4, CFrame.new(0, 0, 0) * CFrame.Angles(0, math.rad(90), 0), function(q)
				table.insert(asked, q)
				return nil, nil
			end)
			-- a quarter turn about y: the mark's +x is the world's -z, its +z the world's +x - exactly, not either way round
			check.is_true(near(asked[1], Vector3.new(-2, 0, 2)))
			check.is_true(near(asked[3], Vector3.new(-2, 0, -2)))
			check.is_true(near(asked[7], Vector3.new(2, 0, 2)))
		end)
		test.case(
			"the mark is laid again when it moved, turned or grew by a share of a cell - not every frame",
			function()
				local at = CFrame.new(5, 0, 5)
				local k = r.wrapKey(8, 16, 16, at)
				check.equal(r.wrapKey(8, 16.05, 16.05, at), k) -- a growing mark: a twentieth of a stud is not a new lay (a cell is 2 studs)
				check.is_true(r.wrapKey(8, 17, 17, at) ~= k) -- half a cell more is
				local lays, last = 0, nil
				for i = 0, 600 do -- ten seconds of growth from 16 to 22 studs, a frame at a time
					local key = r.wrapKey(8, 16 + i * 0.01, 16 + i * 0.01, at)
					if key ~= last then
						lays += 1
						last = key
					end
				end
				check.is_true(lays < 20) -- (keyed to a hundredth of a stud it was laid again on all 601 frames)
				check.is_true(r.wrapKey(8, 16, 16, at * CFrame.Angles(0, math.rad(20), 0)) ~= k) -- turned in place
				check.is_true(r.wrapKey(8, 16, 16, at + Vector3.new(0, 1, 0)) ~= k) -- moved
				check.equal(r.wrapKey(8, 16, 16, CFrame.new(5, 0, 5)), k) -- the same again: the same key
			end
		)
		test.case(
			"the decal layer lays its sheet by this rule, on a client, and falls back to the flat mark",
			function()
				local stage = code("src/kit/VfxStage.luau")
				local has = function(s: string): boolean
					return string.find(stage, s, 1, true) ~= nil
				end
				check.is_true(has("VfxMesh.sheet(cells, cells, box)"))
				check.is_true(has("points = wrapPoints(cells, sz.X, sz.Z, frame, function(from: Vector3)"))
				check.is_true(has("if cells > 0 and isClient then"))
				check.is_true(has("rp.RespectCanCollide = true"))
				check.is_true(has("ch.part.Anchored = true ch.part.CanCollide = false"))
				check.is_true(has("s.set(points, centre)"))
				local mesh = code("src/kit/VfxMesh.luau")
				check.is_true(
					string.find(
						mesh,
						"function VfxMesh.sheet(cols: number, rows: number, reach: number, critical: boolean?)",
						1,
						true
					) ~= nil
				)
			end
		)
	end)
	-- A FRACTURE'S PIECES AS REAL RIGID BODIES ("floor": "world"): run in a Studio play client (18 pieces at rest on a
	-- floor, a step and a ramp); here only that the stage still hands them over as it did there
	test.suite("a fracture's pieces as the engine's own rigid bodies", function()
		test.case(
			"with floor world a piece waits in the slab, is let go with its push, and the kit's own rest stands back",
			function()
				local stage = code("src/kit/VfxStage.luau")
				local has = function(s: string): boolean
					return string.find(stage, s, 1, true) ~= nil
				end
				check.is_true(has('local world = el.floor == "world" and isClient'))
				check.is_true(has("if el.rest == true and not world then"))
				check.is_true(
					has("if ch.wait ~= nil and not ch.let then if t - at < ch.wait then continue end ch.let = true")
				)
				check.is_true(
					has("c.Anchored = false c.AssemblyLinearVelocity = ch.vel c.AssemblyAngularVelocity = ch.spin end")
				)
				check.is_true(has("if not old.Anchored then")) -- a real solid that takes a flying block's place flies on
			end
		)
	end)
end
