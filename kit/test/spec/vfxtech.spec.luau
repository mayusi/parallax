-- vfxtech.spec.luau (kit) — the pro techniques (src/kit/VfxTech.luau) expand into plain layers that the validator,
-- the game and the player already understand: ease, echo, bursts, flicker, rim, boil, path, onDeath.
local frk = require("../frk")
local test, check = frk.test, frk.check

local VfxCompose = require("../../../src/kit/VfxCompose")
local VfxTech = require("../../../src/kit/VfxTech")
local VfxValidate = require("../../../src/kit/VfxValidate")

local function names(out: any): string
	local n = {}
	for _, el in out.layers do
		table.insert(n, el.name)
	end
	return table.concat(n, ",")
end

local function host(layers: { any }): any
	return { version = 3, duration = 2, layers = layers }
end

return function()
	test.suite("VfxTech", function()
		test.case(
			"ease: a { ease, from, to } field becomes keyframes that overshoot (backOut) and end on `to`",
			function()
				local out, issues = VfxCompose.expand(host({
					{
						name = "ring",
						kind = "mesh",
						shape = "ring",
						life = 0.5,
						scale = { ease = "backOut", from = { 1, 1, 1 }, to = { 10, 1, 10 }, keys = 10 },
						transparency = { ease = "quadIn", from = 0, to = 1 },
					},
				}))
				check.equal(#issues, 0)
				local sc = out.layers[1].scale
				check.equal(#sc, 10)
				check.equal(sc[1][1], 0)
				check.equal(sc[10][1], 1)
				check.equal(sc[10][2][1], 10)
				local peak = 0
				for _, kv in sc do
					peak = math.max(peak, kv[2][1])
				end
				check.is_true(peak > 10.5) -- the overshoot
				check.equal(out.layers[1].transparency[12][2], 1)
			end
		)
		test.case("ease: `over` holds the start and the end outside the window; unknown eases are errors", function()
			local keys = VfxTech.easeKeys({ ease = "snap", from = 0, to = 4, keys = 4, over = { 0.2, 0.6 } })
			check.equal(keys[1][1], 0)
			check.equal(keys[2][1], 0.2)
			check.equal(keys[#keys][1], 1)
			check.equal(keys[#keys][2], 4)
			local _, issues = VfxCompose.expand(host({
				{ name = "a", kind = "light", life = 1, brightness = { ease = "wobbly", from = 0, to = 1 } },
			}))
			check.equal(#issues, 1)
			check.is_true(string.find(issues[1].message, "unknown ease", 1, true) ~= nil)
		end)
		test.case("echo: N afterimages, each later, fainter and smaller; the source keeps its outline", function()
			local out, issues = VfxCompose.expand(host({
				{
					name = "slash",
					kind = "mesh",
					shape = "arc",
					at = 0.5,
					life = 0.3,
					outline = true,
					scale = 4,
					transparency = 0.2,
					echo = { count = 3, lag = 0.04, fade = 0.5, shrink = 0.9 },
				},
			}))
			check.equal(#issues, 0)
			check.equal(names(out), "slash,slash_echo1,slash_echo2,slash_echo3")
			check.equal(out.layers[1].echo, nil)
			check.equal(out.layers[1].outline, true)
			check.equal(out.layers[2].at, 0.54)
			check.equal(out.layers[4].at, 0.62)
			check.equal(out.layers[2].transparency, 0.6) -- 1 - 0.8 * 0.5
			check.equal(out.layers[3].transparency, 0.8)
			check.equal(out.layers[2].scale, 3.6)
			check.equal(out.layers[2].outline, nil)
		end)
		test.case("bursts: the emission splits into N cones at different tilts, the rate shared", function()
			local out, issues = VfxCompose.expand(host({
				{
					name = "sparks",
					kind = "sprite",
					at = 1,
					rate = 80,
					["for"] = 0.1,
					bursts = { count = 4, tilt = { 30, 60 }, cone = 15, stagger = 0.02, seed = 5 },
				},
			}))
			check.equal(#issues, 0)
			check.equal(names(out), "sparks_b1,sparks_b2,sparks_b3,sparks_b4")
			local seen = {}
			for k, el in out.layers do
				check.equal(el.rate, 20)
				check.equal(el.spread, 15) -- the key the runtimes read (the spec pinned spreadAngle, which nothing read)
				check.equal(el.at, 1 + (k - 1) * 0.02)
				local tilt = math.sqrt(el.rotate[1] ^ 2 + el.rotate[3] ^ 2)
				check.is_true(tilt >= 29.9 and tilt <= 60.1)
				seen[`{el.rotate[1]},{el.rotate[3]}`] = true
			end
			local distinct = 0
			for _ in seen do
				distinct += 1
			end
			check.equal(distinct, 4)
		end)
		test.case("flicker: a light's brightness becomes a noisy curve around the original, same every run", function()
			local spec = host({
				{
					name = "fire",
					kind = "light",
					life = 2,
					brightness = 4,
					flicker = { amount = 0.3, rate = 10, seed = 1 },
				},
			})
			local a = VfxCompose.expand(spec)
			local b = VfxCompose.expand(spec)
			local keys = a.layers[1].brightness
			check.is_true(#keys >= 20)
			local lo, hi = math.huge, -math.huge
			for i, kv in keys do
				lo, hi = math.min(lo, kv[2]), math.max(hi, kv[2])
				check.equal(kv[2], b.layers[1].brightness[i][2])
				check.is_true(kv[2] >= 4 * 0.7 - 1e-6 and kv[2] <= 4 * 1.3 + 1e-6)
			end
			check.is_true(hi - lo > 0.5)
		end)
		test.case("rim + boil: extra shells round a mesh (ForceField edge, a second scrolling texture)", function()
			local out, issues = VfxCompose.expand(host({
				{
					name = "orb",
					kind = "mesh",
					shape = "sphere",
					life = 1,
					scale = 2,
					texture = "a",
					uvScroll = { 0.2, 0 },
					rim = { color = { 200, 120, 255 } },
					boil = { texture = "b" },
				},
			}))
			check.equal(#issues, 0)
			check.equal(names(out), "orb,orb_rim,orb_boil")
			check.equal(out.layers[2].material, "ForceField")
			check.equal(out.layers[2].texture, nil)
			check.equal(out.layers[2].scale, 2.12)
			check.equal(out.layers[3].texture, "b")
			check.equal(out.layers[3].uvScroll[1], -0.2)
		end)
		test.case("path: a mesh gets a Bézier move; a sprite emitter hops along the curve in windows", function()
			local out, issues = VfxCompose.expand(host({
				{
					name = "orb",
					kind = "mesh",
					shape = "sphere",
					life = 1,
					path = { points = { { 0, 0, 0 }, { 0, 10, 0 }, { 10, 10, 0 } }, keys = 5 },
				},
				{
					name = "trail",
					kind = "sprite",
					point = { 0, 2, 0 },
					at = 0,
					rate = 50,
					["for"] = 0.8,
					path = { points = { { 0, 0, 0 }, { 8, 0, 0 } }, segments = 4 },
				},
			}))
			check.equal(#issues, 0)
			local mv = out.layers[1].move
			check.equal(#mv, 5)
			check.equal(mv[5][2][1], 10)
			check.equal(mv[3][2][2], 7.5) -- the quadratic at t = 0.5: 0.5 * 10 + 0.25 * 10
			check.equal(names(out), "orb,trail_p1,trail_p2,trail_p3,trail_p4")
			check.equal(out.layers[2].point[1], 1)
			check.equal(out.layers[5].point[1], 7)
			check.equal(out.layers[5].at, 0.6)
			check.equal(out.layers[5]["for"], 0.2)
		end)
		test.case("onDeath: a child sprite layer emits where and when the parents die", function()
			local out, issues = VfxCompose.expand(host({
				{
					name = "sparks",
					kind = "sprite",
					at = 0.5,
					count = 30,
					lifetime = { 0.4, 0.6 },
					speed = { 20, 30 },
					onDeath = { texture = "puff", size = 2, ratio = 0.5 },
				},
			}))
			check.equal(#issues, 0)
			check.equal(names(out), "sparks,sparks_death")
			local d = out.layers[2]
			check.equal(d.at, 0.9)
			check.equal(d["for"], 0.2)
			check.equal(d.rate, 75) -- 30 * 0.5 over 0.2 s
			check.equal(d.texture, "puff")
			check.equal(d.shape.size[1], 30) -- reach 15 studs either way
			check.equal(d.onDeath, nil)
		end)
		test.case("haze: a wobbling Glass shell, 0.96..0.99 clear (V4 3.1), round the mesh", function()
			local out, issues = VfxCompose.expand(host({
				{
					name = "fire",
					kind = "mesh",
					shape = "flame",
					life = 1,
					scale = 2,
					texture = "x",
					haze = { strength = 0.4 },
				},
			}))
			check.equal(#issues, 0)
			check.equal(names(out), "fire,fire_haze")
			check.equal(out.layers[2].material, "Glass")
			check.equal(out.layers[2].texture, nil)
			-- strength 0.4 -> 1 - (0.01 + 0.03 x 0.4) = 0.978 (the owner, 2026-11-21: "Yes, remap haze"; was 0.86)
			check.equal(out.layers[2].transparency, 0.978)
			check.equal(out.layers[2].scale, 2.3)
			check.equal(out.layers[2].wobble[2], 6)
		end)
		test.case("mesh-only techniques on another kind are errors, never silently dropped", function()
			local _, issues = VfxCompose.expand(host({ { name = "s", kind = "sprite", echo = { count = 2 } } }))
			check.equal(#issues, 1)
			check.is_true(string.find(issues[1].message, "mesh technique", 1, true) ~= nil)
		end)
	end)

	test.suite("VFX world, shaped light, wind", function()
		local textures = { spark = { grid = 1, id = "", file = "x.png" } }
		local function errorsOf(layers: { any }): string
			local issues = VfxValidate.errors(VfxValidate.preset("t", host(layers), textures))
			local lines = {}
			for _, i in issues do
				table.insert(lines, `{i.path}: {i.message}`)
			end
			return table.concat(lines, "\n")
		end
		test.case("a world layer with every field validates; out-of-range values do not", function()
			check.equal(
				errorsOf({
					{
						name = "w",
						kind = "world",
						at = 0,
						life = 1,
						exposure = { { 0, 0 }, { 0.1, 1.5 }, { 1, 0 } },
						fog = 3,
						fogColor = { 200, 120, 60 },
						fogAmount = 0.6,
						sky = { 255, 150, 80 },
						skyAmount = 0.5,
						sun = 0.3,
						ambient = 2,
						sunRays = 0.4,
						dof = 0.5,
						focus = 40,
						radius = 300,
					},
				}),
				""
			)
			local bad = errorsOf({ { name = "w", kind = "world", life = 1, exposure = 9, dof = 2 } })
			check.is_true(string.find(bad, "exposure", 1, true) ~= nil)
			check.is_true(string.find(bad, "dof", 1, true) ~= nil)
		end)
		test.case("lights take type point | spot | surface with an angle; anything else is an error", function()
			check.equal(
				errorsOf({
					{ name = "a", kind = "light", life = 1, type = "spot", angle = 40, aim = { 0, 0, 10 } },
					{ name = "b", kind = "light", life = 1, type = "surface", size = { 8, 4 }, angle = 120 },
				}),
				""
			)
			check.is_true(
				string.find(errorsOf({ { name = "c", kind = "light", life = 1, type = "laser" } }), "type", 1, true)
					~= nil
			)
		end)
		test.case(
			"lit variants: known sides only, each a registered texture; the default texture is filled in",
			function()
				local out = VfxCompose.expand(host({
					{ name = "s", kind = "sprite", count = 2, lifetime = 1, lit = { left = "spark", top = "spark" } },
				}))
				check.equal(out.layers[1].texture, "spark")
				check.equal(errorsOf(out.layers), "")
				local bad = errorsOf({
					{
						name = "s",
						kind = "sprite",
						texture = "spark",
						count = 2,
						lifetime = 1,
						lit = { below = "spark", left = "nope" },
					},
				})
				check.is_true(string.find(bad, "lit side", 1, true) ~= nil)
				check.is_true(string.find(bad, "nope", 1, true) ~= nil)
			end
		)
		test.case(
			"a big opaque card standing on the ground warns unless it stays upright (FacingCameraWorldUp)",
			function()
				local function warns(layer: any): boolean
					for _, issue in VfxValidate.preset("t", host({ layer }), textures) do
						if issue.severity == "warn" and string.find(issue.message, "camera-facing card", 1, true) then
							return true
						end
					end
					return false
				end
				local ground = {
					name = "surge",
					kind = "sprite",
					texture = "spark",
					count = 1,
					lifetime = 1,
					size = 200,
					point = { 0, 99, 0 },
				}
				check.is_true(warns(ground))
				local upright = table.clone(ground)
				upright.orientation = "FacingCameraWorldUp"
				check.is_true(not warns(upright))
				local glow = table.clone(ground)
				glow.lightEmission = 1
				check.is_true(not warns(glow)) -- an additive glow is not a ground card
				local air = table.clone(ground)
				air.point = { 0, 300, 0 }
				check.is_true(not warns(air)) -- high in the air: its bottom is not on the floor
			end
		)
		test.case(
			"views (impostors): yaw keys to registered textures; the 0-degree view is the default texture",
			function()
				local out = VfxCompose.expand(host({
					{
						name = "s",
						kind = "sprite",
						count = 1,
						lifetime = 1,
						views = { ["0"] = "spark", ["180"] = "spark" },
					},
				}))
				check.equal(out.layers[1].texture, "spark")
				check.equal(errorsOf(out.layers), "")
				local bad = errorsOf({
					{
						name = "s",
						kind = "sprite",
						texture = "spark",
						count = 1,
						lifetime = 1,
						views = { left = "spark", ["90"] = "nope" },
					},
				})
				check.is_true(string.find(bad, "not a yaw", 1, true) ~= nil)
				check.is_true(string.find(bad, "nope", 1, true) ~= nil)
			end
		)
		test.case(
			"onMaterial: real Roblox materials (| alternatives, * fallback) mapping to override tables",
			function()
				check.equal(
					errorsOf({
						{
							name = "dust",
							kind = "sprite",
							texture = "spark",
							count = 4,
							lifetime = 1,
							onMaterial = {
								["Slate|Rock|Concrete"] = { color = { 150, 140, 130 } },
								Water = { mute = true },
								["*"] = {},
							},
						},
					}),
					""
				)
				local bad = errorsOf({
					{
						name = "d",
						kind = "sprite",
						texture = "spark",
						count = 1,
						lifetime = 1,
						onMaterial = { Lava = {}, Metal = { texture = "nope" } },
					},
				})
				check.is_true(string.find(bad, "Lava", 1, true) ~= nil)
				check.is_true(string.find(bad, "nope", 1, true) ~= nil)
			end
		)
		test.case("lens: vignette / aberration / dirt / zoom are 0-1 curves; impact mode invert is known", function()
			check.equal(
				errorsOf({
					{
						name = "l",
						kind = "lens",
						life = 1,
						vignette = { { 0, 0 }, { 0.1, 0.8 }, { 1, 0 } },
						aberration = 0.6,
						dirt = 0.4,
						zoom = { { 0, 1 }, { 1, 0 } },
						color = { 255, 220, 180 },
					},
					{ name = "i", kind = "impact", at = 0.5, life = 0.1, mode = "invert" },
				}),
				""
			)
			check.is_true(
				string.find(errorsOf({ { name = "l", kind = "lens", life = 1, vignette = 3 } }), "vignette", 1, true)
					~= nil
			)
		end)
		test.case(
			"swarm: scripted particles with curl, attraction, floor and trail tables; bad shapes are errors",
			function()
				check.equal(
					errorsOf({
						{
							name = "embers",
							kind = "swarm",
							life = 1.5,
							count = 80,
							point = { 0, 2, 0 },
							lifetime = { 0.6, 1.2 },
							speed = { 2, 6 },
							size = { { 0, 0.4 }, { 1, 0 } },
							color = { 255, 160, 60 },
							curl = { strength = 12, scale = 3 },
							attract = { point = { 0, 4, 0 }, strength = 10, swirl = 30 },
							floor = { y = 0, bounce = 0.5 },
							trail = { lifetime = 0.2 },
							gravity = 10,
							drag = 1,
						},
					}),
					""
				)
				local bad =
					errorsOf({ { name = "s", kind = "swarm", life = 1, count = 900, shape = "Cone", curl = 5 } })
				check.is_true(string.find(bad, "count", 1, true) ~= nil)
				check.is_true(string.find(bad, "shape", 1, true) ~= nil)
				check.is_true(string.find(bad, "curl", 1, true) ~= nil)
			end
		)
		test.case("crater: a radius 0.5..80 and an optional depth", function()
			check.equal(
				errorsOf({ { name = "c", kind = "crater", life = 1.5, point = { 0, 0, 0 }, radius = 8, depth = 3 } }),
				""
			)
			check.is_true(
				string.find(errorsOf({ { name = "c", kind = "crater", life = 1.5, radius = 500 } }), "radius", 1, true)
					~= nil
			)
		end)
		test.case("wind on a sprite needs drag (Roblox lets wind act only through drag)", function()
			local base = { name = "s", kind = "sprite", texture = "spark", count = 4, lifetime = 1 }
			local ok = table.clone(base)
			ok.wind, ok.drag = true, 2
			check.equal(errorsOf({ ok }), "")
			local noDrag = table.clone(base)
			noDrag.wind = true
			check.is_true(string.find(errorsOf({ noDrag }), "drag", 1, true) ~= nil)
		end)
	end)
end
