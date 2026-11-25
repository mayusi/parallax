-- vfxarc.spec.luau (kit) — the slash arc v2 (src/kit/VfxArc.luau, mirrored by the player's arcPoint) and impact frames
-- v4 (the slash drawn from that arc): torn edges, a bowed cross-section, strands, the sweep window, and the validator
-- accepting / refusing the new keys.
local frk = require("../frk")
local test, check = frk.test, frk.check

local VfxArc = require("../../../src/kit/VfxArc")
local VfxValidate = require("../../../src/kit/VfxValidate")

local function near(a: number, b: number): boolean
	return math.abs(a - b) < 1e-9
end

local function host(layers: { any }): any
	return { version = 3, duration = 2, layers = layers }
end

local function errorsOf(layers: { any }): string
	local lines = {}
	for _, i in VfxValidate.errors(VfxValidate.preset("t", host(layers), {})) do
		table.insert(lines, `{i.path}: {i.message}`)
	end
	return table.concat(lines, "\n")
end

return function()
	test.suite("VfxArc (slash arc v2)", function()
		local base = { radius = 7, width = 2.4, arc = 110, taper = 0.95 }

		test.case("no new params: exactly the v1 crescent (presets made before v2 do not move)", function()
			for _, u in { 0, 0.2, 0.5, 0.8, 1 } do
				for _, v in { 0, 0.5, 1 } do
					local x, y, z = VfxArc.point(base, u, v, 0)
					local a = (u - 0.5) * math.rad(110)
					local taper = math.max(math.sin(math.pi * u), 0) ^ 0.95
					local rr = 7 + (v - 0.5) * 2.4 * taper
					check.is_true(near(x, math.sin(a) * rr) and near(y, 0) and near(z, -math.cos(a) * rr))
				end
			end
			check.equal(VfxArc.rows(base), 2)
			check.equal(VfxArc.strands(base), 1)
		end)

		test.case(
			"the sweep lays the whole grid over [tail, head]: pinned to the arc, two points of its own",
			function()
				local _, _, _, ua0 = VfxArc.point(base, 0, 0.5, 0, 0.3, 0.7)
				local _, _, _, ua1 = VfxArc.point(base, 1, 0.5, 0, 0.3, 0.7)
				check.is_true(near(ua0, 0.3) and near(ua1, 0.7))
				-- the window's own ends are points: inner and outer edge meet there
				for _, u in { 0, 1 } do
					local xi, yi, zi = VfxArc.point(base, u, 0, 0, 0.3, 0.7)
					local xo, yo, zo = VfxArc.point(base, u, 1, 0, 0.3, 0.7)
					check.is_true(near(xi, xo) and near(yi, yo) and near(zi, zo))
				end
				-- the window's middle sits on the full arc's 0.5 (where the centreline is the same arc)
				local x, _, z = VfxArc.point(base, 0.5, 0.5, 0, 0.3, 0.7)
				local fx, _, fz = VfxArc.point(base, 0.5, 0.5, 0, 0, 1)
				check.is_true(near(x, fx) and near(z, fz))
			end
		)

		test.case("jag tears the EDGES and never the centreline (the frames' cut stays on the blade's path)", function()
			local torn = table.clone(base)
			torn.jag, torn.seed = 0.3, 4
			local moved = 0
			for _, u in { 0.1, 0.3, 0.5, 0.7, 0.9 } do
				local x, y, z = VfxArc.point(torn, u, 0.5, 0)
				local cx, cy, cz = VfxArc.point(base, u, 0.5, 0)
				check.is_true(near(x, cx) and near(y, cy) and near(z, cz))
				local ex, _, ez = VfxArc.point(torn, u, 0, 0)
				local bx, _, bz = VfxArc.point(base, u, 0, 0)
				if math.abs(ex - bx) + math.abs(ez - bz) > 1e-3 then
					moved += 1
				end
			end
			check.is_true(moved >= 4)
		end)

		test.case(
			"ridge bows the band out of its plane: depth at the centreline, the edges stay in the plane",
			function()
				local ridged = { radius = 8, width = 3, arc = 172, taper = 0.95, vertical = 1, ridge = 0.4 }
				check.equal(VfxArc.rows(ridged), 6)
				local _, _, zc = VfxArc.point(ridged, 0.5, 0.5, 0)
				local _, _, ze = VfxArc.point(ridged, 0.5, 0, 0)
				check.is_true(near(zc, 0.4 * 3) and near(ze, 0))
			end
		)

		test.case(
			"strands: the middle of three IS the single crescent; the outer ones thinner and set behind",
			function()
				local three = table.clone(base)
				three.strands = 3
				for _, u in { 0.2, 0.5, 0.8 } do
					for _, v in { 0, 0.5, 1 } do
						local x, y, z = VfxArc.point(three, u, v, 1)
						local sx, sy, sz = VfxArc.point(base, u, v, 0)
						check.is_true(near(x, sx) and near(y, sy) and near(z, sz))
					end
				end
				local _, yo = VfxArc.point(three, 0.5, 0.5, 0)
				check.is_true(yo < 0) -- the flat arc's depth axis is Y: the outer strand sits below / behind
				local xi, _, zi = VfxArc.point(three, 0.5, 0, 0)
				local xo, _, zo = VfxArc.point(three, 0.5, 1, 0)
				check.is_true(math.sqrt((xo - xi) ^ 2 + (zo - zi) ^ 2) < 2.4) -- thinner than the core strand's 2.4
			end
		)
	end)

	test.suite("VFX slash keys (arc sweep, impact frames v4)", function()
		local arc = { name = "a", kind = "mesh", shape = "arc", params = { radius = 5, jag = 0.2, strands = 2 } }

		test.case("sweep on an arc is valid; on another shape, or malformed, it is an error", function()
			local ok = table.clone(arc)
			ok.sweep = { head = { { 0, 0 }, { 0.3, 1 }, { 1, 1 } }, tail = { { 0, 0 }, { 0.4, 0 }, { 1, 1 } } }
			check.equal(errorsOf({ ok }), "")
			local ring = { name = "r", kind = "mesh", shape = "ring", sweep = { head = 1 } }
			check.is_true(string.find(errorsOf({ ring }), "shape must be arc", 1, true) ~= nil)
			local bad = table.clone(arc)
			bad.sweep = { head = 2 }
			check.is_true(errorsOf({ bad }) ~= "")
			-- both move the arc's vertices: wobble would restore the full arc under the sweep every frame (review)
			local both = table.clone(ok)
			both.wobble = { 0.2, 3, 4 }
			check.is_true(string.find(errorsOf({ both }), "use one", 1, true) ~= nil)
		end)

		test.case("a frame may stroke and split the cut, run its lines along it and frame it square", function()
			local frame = {
				name = "f",
				kind = "impact",
				style = "frame",
				at = 0,
				life = 0.06,
				lines = "cut",
				camera = "cut",
				draw = { slash = 1.4, split = 1, slide = 0.04, cutSmear = 1.5 },
			}
			check.equal(errorsOf({ frame }), "")
			local wrong = table.clone(frame)
			wrong.draw = { slashh = 1 }
			check.is_true(string.find(errorsOf({ wrong }), "unknown draw knob", 1, true) ~= nil)
			local far = table.clone(frame)
			far.draw = { slide = 0.9 }
			check.is_true(errorsOf({ far }) ~= "")
		end)
	end)

	test.suite("VFX research techniques (2026-10-23: kick, streaks, flare, unread keys)", function()
		local function warnsOf(layers: { any }): string
			local lines = {}
			for _, i in VfxValidate.preset("t", host(layers), {}) do
				if i.severity == "warn" then
					table.insert(lines, i.message)
				end
			end
			return table.concat(lines, " | ")
		end

		test.case(
			"a shake may kick the picture in the strike's direction; a wild or malformed kick is an error",
			function()
				local ok = { name = "k", kind = "shake", life = 0.5, amplitude = 1, kick = { 0, -4 } }
				check.equal(errorsOf({ ok }), "")
				check.is_true(errorsOf({ { name = "k", kind = "shake", kick = { 30, 0 } } }) ~= "")
				check.is_true(errorsOf({ { name = "k", kind = "shake", kick = 3 } }) ~= "")
			end
		)

		test.case("shake / fov refuse keys the stage never reads; the two v2 names only warn (judged looks)", function()
			-- the bug that started it: a fov layer keyed `amount` never punched
			check.is_true(
				string.find(errorsOf({ { name = "f", kind = "fov", amount = 10 } }), "not read", 1, true) ~= nil
			)
			check.equal(errorsOf({ { name = "f", kind = "fov", fov = 10 } }), "")
			check.is_true(
				string.find(warnsOf({ { name = "f", kind = "fov", fov = 10 } }), "never plays", 1, true) ~= nil
			)
			check.equal(errorsOf({ { name = "s", kind = "shake", frequency = 30 } }), "")
			check.is_true(
				string.find(warnsOf({ { name = "s", kind = "shake", frequency = 30 } }), "not read", 1, true) ~= nil
			)
		end)

		test.case("lens streaks take an angle and a speed; a frame takes a Kanada flare", function()
			check.equal(
				errorsOf({ { name = "l", kind = "lens", streaks = 0.8, streakAngle = -70, streakSpeed = 2 } }),
				""
			)
			check.is_true(errorsOf({ { name = "l", kind = "lens", streaks = 2 } }) ~= "")
			-- (a lens layer's point and aim are points: one that is none was read as the origin, and never said)
			check.is_true(errorsOf({ { name = "l", kind = "lens", streaks = 0.5, point = "nowhere" } }) ~= "")
			check.is_true(errorsOf({ { name = "l", kind = "lens", streaks = 0.5, aim = 7 } }) ~= "")
			check.equal(
				errorsOf({ { name = "l", kind = "lens", streaks = 0.5, point = { 0, 30, -80 }, aim = { 0, 0, 0 } } }),
				""
			)
			local frame = { name = "x", kind = "impact", style = "frame", at = 0, life = 0.05, draw = { flare = 1.5 } }
			check.equal(errorsOf({ frame }), "")
		end)

		test.case("a crown is a mesh shape (a liquid coronet: flaring wall, rolled lip, scalloped rim)", function()
			check.equal(
				errorsOf({
					{
						name = "c",
						kind = "mesh",
						at = 0,
						life = 1,
						point = { 0, 0, 0 },
						shape = "crown",
						params = { radius = 1.75, base = 1, height = 1.6, lip = 0.2, scallops = 18 },
					},
				}),
				""
			)
		end)

		test.case("frames is a boolean; a crown's scallops a whole number (review 2026-10-25)", function()
			local function m(extra: any): any
				local el = {
					name = "c",
					kind = "mesh",
					at = 0,
					life = 1,
					point = { 0, 0, 0 },
					shape = "crown",
					params = { scallops = 18 },
				}
				for k, v in extra do
					el[k] = v
				end
				return el
			end
			check.equal(errorsOf({ m({ frames = false }) }), "")
			check.is_true(errorsOf({ m({ frames = "false" }) }) ~= "")
			check.is_true(errorsOf({ m({ params = { scallops = 17.5 } }) }) ~= "")
			check.equal(errorsOf({ m({ params = { scallops = 0 } }) }), "")
		end)

		test.case("a torus is a mesh shape (a smoke ring / halo); an unknown shape is refused", function()
			check.equal(
				errorsOf({
					{
						name = "t",
						kind = "mesh",
						at = 0,
						life = 1,
						point = { 0, 0, 0 },
						shape = "torus",
						params = { radius = 2, tube = 0.6 },
					},
				}),
				""
			)
			check.is_true(
				errorsOf({ { name = "t", kind = "mesh", at = 0, life = 1, point = { 0, 0, 0 }, shape = "donut" } })
					~= ""
			)
		end)

		test.case(
			"a mesh's spin takes keys of its SPEED over life (a whirl that spins up); a twisted flame shell",
			function()
				local function mesh(spin: any): any
					return {
						name = "w",
						kind = "mesh",
						at = 0,
						life = 2,
						point = { 0, 0, 0 },
						shape = "flame",
						params = { radius = 1, height = 6, twist = 220 },
						spin = spin,
					}
				end
				check.equal(errorsOf({ mesh({ 0, 90, 0 }) }), "")
				check.equal(
					errorsOf({ mesh({ { 0, { 0, 60, 0 } }, { 0.7, { 0, 900, 0 } }, { 1, { 0, 200, 0 } } }) }),
					""
				)
				check.is_true(errorsOf({ mesh(90) }) ~= "") -- a bare number is not a spin
				check.is_true(errorsOf({ mesh({ { 0, 60 }, { 1, 900 } }) }) ~= "") -- keys of numbers, not [x, y, z]
			end
		)

		test.case("a swarm's attract and drag take curves over the layer's life (an implosion that lets go)", function()
			local function swarm(extra: any): any
				local el = { name = "s", kind = "swarm", at = 0, life = 2, count = 20, point = { 0, 0, 0 } }
				for k, v in extra do
					el[k] = v
				end
				return el
			end
			check.equal(
				errorsOf({
					swarm({
						attract = {
							point = { 0, 9, 0 },
							strength = { { 0, 6 }, { 0.3, 80 }, { 0.31, 0 }, { 1, 0 } },
							swirl = 40,
						},
						drag = { { 0, 1 }, { 0.28, 1 }, { 0.281, 50 }, { 0.3, 50 }, { 0.301, 0.2 }, { 1, 0.2 } },
					}),
				}),
				""
			)
			check.is_true(errorsOf({ swarm({ drag = { { 0, 1 }, { 1, 80 } } }) }) ~= "") -- drag tops out at 50
			check.is_true(errorsOf({ swarm({ attract = { point = { 0, 0, 0 }, strength = { { 0, 1 } } } }) }) ~= "") -- one key
		end)

		test.case(
			"a part's scale reaches its meshes (an eased scale, or none) - the shock_ring at 0.42 stayed full size",
			function()
				local VfxCompose = require("../../../src/kit/VfxCompose")
				local part = {
					points = { ground = { 0, 0, 0 } },
					layers = {
						{
							name = "crest",
							kind = "mesh",
							at = 0,
							life = 1,
							point = "ground",
							shape = "arc",
							params = { radius = 2, width = 0.4 },
							scale = { ease = "expoOut", from = { 1, 1, 1 }, to = { 13, 5, 13 }, keys = 4 },
						},
						{
							name = "plain",
							kind = "mesh",
							at = 0,
							life = 1,
							point = "ground",
							shape = "arc",
							params = { radius = 2 },
						},
					},
				}
				local out = VfxCompose.expand(
					{ version = 3, duration = 2, layers = {}, use = { { part = "ring", as = "r", scale = 0.5 } } },
					{
						parts = function(name: string): any
							return if name == "ring" then part else nil
						end,
					}
				)
				local crest, plain
				for _, el in out.layers do
					if el.name == "r.crest" then
						crest = el
					elseif el.name == "r.plain" then
						plain = el
					end
				end
				check.is_true(crest ~= nil and plain ~= nil)
				check.is_true(near(crest.params.radius, 2)) -- the mesh is built at 1 and scaled whole
				local last = crest.scale[#crest.scale][2]
				check.is_true(near(last[1], 6.5) and near(last[2], 2.5))
				check.is_true(near(plain.scale[1], 0.5) and near(plain.scale[3], 0.5))
			end
		)
	end)
end
