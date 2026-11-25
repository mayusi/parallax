-- vfxrockring.spec.luau (kit) — the crater on a PART floor (src/kit/VfxRockRing.luau; LIMITATIONS_FIXES_V4 3.4 step 3
-- "non-terrain fracture rings", 13.3.4 "non-terrain rock ring decals"): which ground is carved and which gets the ring,
-- the ring's plan, its rise and fade; the browser player's copy run in node gives the same numbers; VfxStage and the
-- validator use it; the mark's texture is a kit texture spec.
local frk = require("../frk")
local fs = require("@lune/fs")
local process = require("@lune/process")
local serde = require("@lune/serde")
local test, check = frk.test, frk.check

local VfxRockRing = require("../../../src/kit/VfxRockRing")
local VfxValidate3 = require("../../../src/kit/VfxValidate3")

local function code(path: string): string
	local out = {}
	for line in string.gmatch(fs.readFile(path), "[^\n]+") do
		local cut = string.find(line, "--", 1, true)
		table.insert(out, if cut then string.sub(line, 1, cut - 1) else line)
	end
	return (string.gsub(table.concat(out, " "), "%s+", " "))
end

return function()
	test.suite("VfxRockRing", function()
		test.case("terrain is carved, a part gets the ring, nothing gets nothing", function()
			check.equal(VfxRockRing.ground({ terrain = true }), "terrain")
			check.equal(VfxRockRing.ground({ terrain = false }), "part")
			check.equal(VfxRockRing.ground(nil), "none")
		end)

		test.case("the plan: round the rim, every chunk its own, the same seed the same ring", function()
			for _, r in { 2, 6, 14, 40 } do
				local plan = VfxRockRing.plan(r, 7)
				check.equal(#plan, VfxRockRing.count(r))
				check.is_true(#plan >= 6 and #plan <= 18)
				local angles = {}
				for i, rock in plan do
					check.is_true(rock.distance >= r * 0.9 and rock.distance <= r * 1.13)
					check.is_true(rock.tilt >= math.rad(20) - 1e-9 and rock.tilt <= math.rad(45) + 1e-9)
					for _, s in rock.size do
						check.is_true(s > 0 and s < r)
					end
					angles[i] = rock.angle
				end
				for i = 2, #angles do
					check.is_true(angles[i] > angles[i - 1]) -- in order round the ring: never two on one spot
				end
				check.is_true(angles[#angles] - angles[1] > math.pi) -- all the way round
				local again = VfxRockRing.plan(r, 7)
				check.equal(again[3].yaw, plan[3].yaw)
				check.is_true(VfxRockRing.plan(r, 8)[3].yaw ~= plan[3].yaw)
			end
			check.equal(#VfxRockRing.plan(6, 1, 0), 0) -- rocks = 0: the mark alone
			check.equal(#VfxRockRing.plan(6, 1, 25), 25)
		end)

		test.case("the hash is even and stays in 0..1", function()
			local sum, lo, hi = 0, 1, 0
			for i = 1, 2000 do
				local h = VfxRockRing.hash(i, 3, 11)
				sum += h
				lo, hi = math.min(lo, h), math.max(hi, h)
			end
			check.is_true(lo >= 0 and hi < 1)
			check.is_true(math.abs(sum / 2000 - 0.5) < 0.03)
		end)

		test.case("chunks burst up, hold, sink back; the mark fades only at the end", function()
			local life = 2
			check.equal(VfxRockRing.rise(0, life), 0)
			check.is_true(VfxRockRing.rise(0.06, life) > 1) -- the overshoot of the burst
			check.is_true(math.abs(VfxRockRing.rise(0.08, life) - 1) < 1e-9)
			check.is_true(math.abs(VfxRockRing.rise(1.2, life) - 1) < 1e-9)
			check.is_true(VfxRockRing.rise(1.8, life) < 1 and VfxRockRing.rise(1.8, life) > 0)
			check.equal(VfxRockRing.rise(2, life), 0)
			check.equal(VfxRockRing.fade(1.0, life), 0)
			check.is_true(math.abs(VfxRockRing.fade(1.75, life) - 0.5) < 1e-9)
			check.equal(VfxRockRing.fade(2.5, life), 1)
			check.equal(VfxRockRing.decalWidth(3.2), 10)
		end)

		test.case("the browser player's copy gives the same plan, rise and fade (node)", function()
			local js = fs.readFile("kit/vfx/player/player.js")
			local a = string.find(js, "function rockRingMul32(", 1, true)
			local b = string.find(js, "\n// crater: the game carves terrain", a, true)
			check.is_true(a ~= nil and b ~= nil)
			local cases = {}
			for _, r in { 1.5, 3.5, 6, 12.25, 40 } do
				for _, seed in { 1, 2, 77, 4096 } do
					for _, count in { false, 0, 9 } do
						table.insert(cases, {
							r = r,
							seed = seed,
							count = count,
							plan = VfxRockRing.plan(r, seed, if count == false then nil else count :: number),
						})
					end
				end
			end
			local times = {}
			for _, t in { -1, 0, 0.03, 0.08, 0.5, 1.4, 1.6, 1.99, 2, 3 } do
				table.insert(times, { t = t, rise = VfxRockRing.rise(t, 2), fade = VfxRockRing.fade(t, 2) })
			end
			local script = string.sub(js, a, b)
				.. "\nconst cases = "
				.. serde.encode("json", cases)
				.. ";\nconst times = "
				.. serde.encode("json", times)
				.. ";\nlet bad = 0, n = 0; const near = (x, y) => Math.abs(x - y) < 1e-9;"
				.. "\nfor (const c of cases) { const got = rockRingPlan(c.r, c.seed, c.count === false ? undefined : c.count); n++;"
				.. " const want = Array.isArray(c.plan) ? c.plan : []; c.plan = want;" -- (an empty Luau table encodes as {})
				.. " if (got.length !== want.length) { bad++; continue; }"
				.. " got.forEach((g, i) => { const w = c.plan[i]; if (!near(g.angle, w.angle) || !near(g.distance, w.distance) || !near(g.tilt, w.tilt) || !near(g.yaw, w.yaw) || g.size.some((s, k) => !near(s, w.size[k]))) { bad++; console.log(JSON.stringify(c.r), i); } }); }"
				.. "\nfor (const x of times) { n++; if (!near(rockRingRise(x.t, 2), x.rise) || !near(rockRingFade(x.t, 2), x.fade)) { bad++; console.log('time', x.t); } }"
				.. "\nconsole.log('MISMATCH ' + bad + ' of ' + n);"
			fs.writeFile("build/vfxrockring_parity.js", script)
			local r = process.exec("node", { "build/vfxrockring_parity.js" })
			fs.removeFile("build/vfxrockring_parity.js")
			check.is_true(r.ok, r.stderr)
			check.is_true(string.find(r.stdout, "MISMATCH 0 of", 1, true) ~= nil, r.stdout)
		end)

		test.case(
			"VfxStage lays the ring on a part and still carves terrain; the player draws it on a part floor",
			function()
				local stage = code("src/kit/VfxStage.luau")
				local function has(s: string): boolean
					return string.find(stage, s, 1, true) ~= nil
				end
				check.is_true(has('local VfxRockRing = require("./VfxRockRing")'))
				check.is_true(
					has("mode = VfxRockRing.ground(if hit then { terrain = hit.Instance == terrain } else nil)")
				)
				check.is_true(has('if mode == "part" and hit then layRing(hit)'))
				check.is_true(has("VfxRockRing.plan(r, el.seed or 1, el.rocks)"))
				check.is_true(has("mark.Color3 = floorPart.Color"))
				check.is_true(has("p.Material = floorPart.Material"))
				check.is_true(has("terrain:FillBall(centre, r, Enum.Material.Air)")) -- terrain: carved as before
				check.is_true(has("table.insert(cleanups, dropRing)"))
				local js = fs.readFile("kit/vfx/player/player.js")
				check.is_true(
					string.find(js, "if (player.partFloor) { this.buildRing(player, el); return; }", 1, true) ~= nil
				)
				check.is_true(string.find(js, "this.partFloor = plate.material.color.clone();", 1, true) ~= nil)
			end
		)

		test.case("the mark is a kit texture; the validator reads the crater's rocks / seed / texture", function()
			if fs.isFile("assets/textures/rock_ring.json") then -- (a project's texture: the kit's own repo has none)
				local spec = serde.decode("json", fs.readFile("assets/textures/rock_ring.json"))
				check.equal(spec.engine, "fx")
				check.equal(spec.recipe, "comp")
			end
			local textures = { rock_ring = { id = "", grid = 1 } }
			local function preset(extra: { [string]: any }): any
				local layer: { [string]: any } =
					{ name = "ring", kind = "crater", at = 0, life = 2, point = { 0, 0, 0 }, radius = 4 }
				for k, v in extra do
					layer[k] = v
				end
				return { version = 3, duration = 3, layers = { layer } }
			end
			local function errors(p: any): number
				local n = 0
				for _, issue in VfxValidate3.preset("t", p, textures) do
					if issue.severity == "error" then
						n += 1
					end
				end
				return n
			end
			check.equal(errors(preset({ rocks = 8, seed = 3, texture = "rock_ring" })), 0)
			check.is_true(errors(preset({ rocks = 99 })) > 0)
			check.is_true(errors(preset({ texture = "no_such_mark" })) > 0)
			check.is_true(errors(preset({ seed = -1 })) > 0)
		end)
	end)
end
