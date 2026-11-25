-- worldlight.spec.luau (kit) — W5, A WORLD'S LIGHT PASS (LIMITATIONS_FIXES_V4 5.1 / 5.4 / 13.5: "W5 kit world light
-- (LightingStyle.Realistic, <= 16 shadow lights)"; card ut7p: GothicCourtyard's 52 lamps all Shadows = false, the
-- night pitch black outside three of them). kit/lib/worldlight.luau.
-- Held here: the picker never puts more than `most` shadow lamps within 120 studs of one (a dense square of 60 lamps,
-- a long street of 200), takes the brightest first, never two a pace apart; a blueprint's "shadows": "auto" sets
-- every lamp's Shadows by it (a lamp's own word kept) and the world's shadow budget check stays quiet; a bad
-- "shadows" is an error; the five presets compile with LightingStyle Realistic, a style Roblox lacks is an error.
-- Not claimed: how the presets read (the owner's eye, in Studio).
local frk = require("../frk")
local test, check = frk.test, frk.check

local Environment = require("../../lib/environment")
local Light = require("../../lib/worldlight")
local World = require("../../lib/world")

local function lcg(seed: number): () -> number
	local s = seed
	return function()
		s = (s * 48271) % 2147483647
		return s / 2147483647
	end
end

local function square(n: number, side: number, seed: number): { Light.Lamp }
	local rnd = lcg(seed)
	local out = {}
	for _ = 1, n do
		table.insert(out, { x = rnd() * side, z = rnd() * side, range = 10 + rnd() * 30, brightness = 0.5 + rnd() * 3 })
	end
	return out
end

-- a world of lamps on posts: { x, z, range, brightness, shadows? }
local function compile(lamps: { any }, shadows: any?): ({ any }, { any }, any)
	local build: { any } = {
		{ floor = { name = "Court", center = { 0, 0, 0 }, size = { 400, 400 }, mat = "stone" } },
	}
	for i, l in lamps do
		table.insert(build, {
			part = {
				name = `Lamp{i}`,
				size = { 1, 8, 1 },
				pos = { l[1], 4, l[2] },
				mat = "iron",
				light = { range = l[3], brightness = l[4], color = { 255, 180, 110 }, shadows = l[5] },
			},
		})
	end
	local _, parts, issues, extras = World.compile({
		name = "LightSpec",
		palette = {
			stone = { material = "Slate", color = { 60, 62, 70 } },
			iron = { material = "Metal", color = { 30, 30, 32 } },
		},
		lighting = "gothic_moonlit",
		shadows = shadows,
		build = build,
	}, { meshes = {} })
	return parts, issues, extras
end

local function casting(parts: { any }): number
	local n = 0
	for _, p in parts do
		for _, c in p.children or {} do
			if c.kind == "light" and c.spec.shadows == true then
				n += 1
			end
		end
	end
	return n
end

return function()
	test.suite("W5: the light pass", function()
		test.case("a dense square: at most 16 shadow lamps within 120 studs, the brightest first", function()
			for seed = 1, 6 do
				local lamps = square(60, 100, seed)
				local chosen = Light.pick(lamps)
				check.truthy(#chosen >= 8 and #chosen <= 16, `{#chosen} chosen`)
				check.truthy(Light.worst(lamps, chosen) <= 16, `worst {Light.worst(lamps, chosen)}`)
				-- the very brightest-widest lamp is always among them
				local best, bs = 1, -1
				for i, l in lamps do
					if l.brightness * l.range > bs then
						best, bs = i, l.brightness * l.range
					end
				end
				check.equal(chosen[1], best)
			end
		end)

		test.case("a long street: more than 16 cast in all, never more than 16 near any one", function()
			local lamps = {}
			for i = 0, 199 do
				table.insert(lamps, { x = i * 12, z = (i % 2) * 14, range = 24, brightness = 2 })
			end
			local chosen = Light.pick(lamps)
			check.truthy(#chosen > 16, `{#chosen} along 2.4 km`)
			check.truthy(Light.worst(lamps, chosen) <= 16, `worst {Light.worst(lamps, chosen)}`)
			-- and a budget of 4
			check.truthy(Light.worst(lamps, Light.pick(lamps, 4)) <= 4)
		end)

		test.case("two lamps a pace apart throw one shadow", function()
			local chosen = Light.pick({
				{ x = 0, z = 0, range = 20, brightness = 3 },
				{ x = 2, z = 0, range = 20, brightness = 2 },
				{ x = 40, z = 0, range = 20, brightness = 1 },
			})
			check.equal(#chosen, 2)
			check.equal(chosen[1], 1)
			check.equal(chosen[2], 3)
		end)

		test.case('"shadows": "auto" sets every lamp by the picker; the budget check stays quiet', function()
			local lamps = {}
			local rnd = lcg(7)
			for _ = 1, 40 do
				table.insert(lamps, { rnd() * 160 - 80, rnd() * 160 - 80, 12 + rnd() * 20, 1 + rnd() * 2 })
			end
			local parts, issues, extras = compile(lamps)
			check.equal(casting(parts), 0) -- (no pass asked: no lamp casts, as before)
			parts, issues, extras = compile(lamps, "auto")
			local n = casting(parts)
			check.truthy(n >= 8, `{n} cast`) -- (160 studs a side: two 120-stud reaches, so more than 16 in all)
			-- measured on the parts themselves: no shadow lamp has more than 16 within 120 studs
			local at = {}
			for _, p in parts do
				for _, c in p.children or {} do
					if c.kind == "light" and c.spec.shadows == true then
						table.insert(at, p.pos)
					end
				end
			end
			for _, a in at do
				local near = 0
				for _, b in at do
					near += if (a[1] - b[1]) ^ 2 + (a[3] - b[3]) ^ 2 <= 120 * 120 then 1 else 0
				end
				check.truthy(near <= 16, `{near} shadow lamps near one`)
			end
			check.equal(extras.shadows.casters, n)
			check.truthy(extras.shadows.worst <= 16)
			for _, i in issues do
				check.truthy(
					not string.find(i.message, "lights that cast shadows", 1, true),
					`the budget check spoke: {i.message}`
				)
			end
		end)

		test.case("a lamp's own word is kept, a bad budget is an error", function()
			local parts = compile({ { 0, 0, 30, 3, false }, { 50, 0, 20, 1 } }, { most = 16 })
			for _, p in parts do
				for _, c in p.children or {} do
					if p.name == "Lamp1" then
						check.equal(c.spec.shadows, false)
					elseif p.name == "Lamp2" then
						check.equal(c.spec.shadows, true)
					end
				end
			end
			local _, issues = compile({ { 0, 0, 30, 3 } }, { most = 99 })
			local said = false
			for _, i in issues do
				said = said or (i.severity == "error" and i.path == "shadows")
			end
			check.truthy(said)
		end)

		test.case("five Realistic presets compile; a style Roblox lacks is an error", function()
			check.equal(#Light.NAMES, 5)
			for _, name in Light.NAMES do
				local env, issues = Environment.compile({ lighting = name })
				check.equal(#issues, 0)
				check.equal((env :: any).lighting.lightingStyle, "Realistic")
				check.truthy((env :: any).lighting.clockTime ~= nil)
			end
			local _, issues = Environment.compile({ lighting = { preset = "gothic_fog", lightingStyle = "Cinematic" } })
			check.truthy(#issues == 1 and issues[1].path == "lighting.lightingStyle")
		end)
	end)
end
