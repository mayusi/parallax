-- vfxplate.spec.luau (kit) — B4 impact plates stepped on the 60 fps clock (src/kit/VfxPlate.luau;
-- LIMITATIONS_FIXES_V4 §3.4 step 3). What is proven: a drawing is held `rate` frames (on ones, twos, threes); a
-- one-shot plate is over after its last drawing, a loop wraps, a hold keeps the last; each cell's rectangle is its own
-- part of the sheet (no two overlap, together they tile it); a sheet that is not 1 / 4 / 16 cells is refused; and the
-- plates the kit ships (assets/effects/plates) are ones it plays.
local frk = require("../frk")
local fs = require("@lune/fs")
local serde = require("@lune/serde")
local test, check = frk.test, frk.check

local VfxPlate = require("../../../src/kit/VfxPlate")

return function()
	test.suite("VfxPlate", function()
		test.case("a drawing is held `rate` frames; one-shot ends, loop wraps, hold keeps the last", function()
			local spec = { frames = 16, rate = 2 }
			check.equal(VfxPlate.cellAt(spec, 0), 0)
			check.equal(VfxPlate.cellAt(spec, 1), 0)
			check.equal(VfxPlate.cellAt(spec, 2), 1)
			check.equal(VfxPlate.cellAt(spec, 31), 15)
			check.equal(VfxPlate.cellAt(spec, 32), nil)
			check.equal(VfxPlate.cellAt(spec, 32, "Loop"), 0)
			check.equal(VfxPlate.cellAt(spec, 99, "Hold"), 15)
			check.equal(VfxPlate.cellAt({ frames = 4, rate = 1 }, 3), 3)
			check.equal(VfxPlate.cellAt({ frames = 4, rate = 3 }, 5), 1)
			check.equal(VfxPlate.cellAt(spec, -1), nil)
			check.equal(VfxPlate.cellAt(spec, 0 / 0), nil)
		end)

		test.case("each cell's rectangle is its own: together they tile the sheet", function()
			for _, frames in { 1, 4, 16 } do
				local spec = { frames = frames }
				local cols = VfxPlate.layout(spec)
				local seen = {}
				local area = 0
				for c = 0, frames - 1 do
					local ox, oy, w, h = VfxPlate.rect(spec, c, 1024)
					check.equal(w, 1024 / cols)
					check.equal(h, 1024 / cols)
					local key = `{ox},{oy}`
					check.is_true(seen[key] == nil)
					seen[key] = true
					check.is_true(ox >= 0 and oy >= 0 and ox + w <= 1024 and oy + h <= 1024)
					area += w * h
				end
				check.equal(area, 1024 * 1024)
			end
			local _, oy = VfxPlate.rect({ frames = 16 }, 5, 1024)
			check.equal(oy, 256) -- cell 5 of a 4 x 4: the second row
		end)

		test.case("a sheet that is not 1, 4 or 16 cells is refused", function()
			for _, bad in { { frames = 9 }, { frames = 0 }, {}, "x" } do
				check.is_true(not pcall(VfxPlate.layout, bad))
			end
		end)

		test.case(
			"the shipped plates are plates it plays, each carrying its own id (not in the fx registry)",
			function()
				local dir = "assets/effects/plates"
				if not fs.isDir(dir) or not fs.isFile("assets/effects/_textures.json") then
					return -- (shipped plates are a project's effects: the kit's own repo has none)
				end
				local reg = serde.decode("json", fs.readFile("assets/effects/_textures.json"))
				local n = 0
				for _, f in fs.readDir(dir) do
					if string.sub(f, -11) == ".plate.json" then
						n += 1
						local spec = serde.decode("json", fs.readFile(dir .. "/" .. f))
						local cols = VfxPlate.layout(spec)
						check.equal(cols * cols, spec.frames)
						check.is_true(type(spec.id) == "string")
						-- the fx registry needs a texture spec the build makes for every entry: a plate is not one
						check.is_true(reg[spec.texture] == nil)
					end
				end
				check.is_true(n >= 1)
			end
		)
	end)
end
