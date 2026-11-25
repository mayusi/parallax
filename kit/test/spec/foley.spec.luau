-- foley.spec.luau — FoleyRules (src/kit): surfaces, stride, walk / run, landings; and every sound the rules can ask
-- for exists in the footsteps set (assets/sounds/sets/footsteps.json), so the runtime never plays a missing name.
local frk = require("../frk")
local test, check = frk.test, frk.check

local fs = require("@lune/fs")
local serde = require("@lune/serde")

local Rules = require("../../../src/kit/FoleyRules")

return function()
	test.suite("FoleyRules", function()
		test.case("the floor's material picks the surface; air is no step; the unknown is dirt", function()
			check.equal(Rules.surface("LeafyGrass"), "grass")
			check.equal(Rules.surface("Cobblestone"), "stone")
			check.equal(Rules.surface("WoodPlanks"), "wood")
			check.equal(Rules.surface("Air"), nil)
			check.equal(Rules.surface("Neon"), "dirt")
			check.equal(Rules.surface(5), nil)
		end)
		test.case("a game's overrides remap a material; junk in them is ignored; air stays no step", function()
			local o = { Grass = "drygrass", Rock = 5 :: any }
			check.equal(Rules.surface("Grass", o), "drygrass")
			check.equal(Rules.surface("LeafyGrass", o), "grass")
			check.equal(Rules.surface("Rock", o), "stone")
			check.equal(Rules.surface("Air", { Air = "grass" }), nil)
			check.equal(Rules.stepSound("Grass", 24, o), "boot_step_drygrass_heavy")
		end)
		test.case(
			"a walk steps every 0.35 s, a sprint faster, never below 0.22 s; standing still never steps",
			function()
				check.is_true(math.abs((Rules.interval(16) :: number) - 0.35) < 1e-9)
				check.is_true((Rules.interval(24) :: number) < (Rules.interval(16) :: number))
				check.equal(Rules.interval(200), 0.22)
				check.equal(Rules.interval(0.5), nil)
				check.equal(Rules.interval(0 / 0), nil)
				-- speed exactly 2 returns an interval (not nil); < 2 is the threshold (kills < -> <= and 2 -> 3 mutants)
				check.is_true(Rules.interval(2) ~= nil)
				-- speed 1.9 is below the threshold and returns nil
				check.equal(Rules.interval(1.9), nil)
				-- slow speed (3) is clamped to 0.6 upper bound; mutant upper=1.6 returns STRIDE/3 ~1.87 (kills 0.6 -> 1.6)
				check.equal(Rules.interval(3), 0.6)
			end
		)
		test.case("walk = light, run = heavy; a hop is silent, a drop lands", function()
			check.equal(Rules.stepSound("Grass", 16), "boot_step_grass_light")
			check.equal(Rules.stepSound("Slate", 22), "boot_step_stone_heavy")
			check.equal(Rules.stepSound("Air", 16), nil)
			check.equal(Rules.landSound(10), nil)
			check.equal(Rules.landSound(40), "land_light")
			check.equal(Rules.landSound(90), "land_heavy")
			check.equal(Rules.landSound(0 / 0), nil)
			-- exactly at RUN_SPEED=20: heavy (kills >= -> > and 20 -> 21 mutants)
			check.equal(Rules.weight(20), "heavy")
			check.equal(Rules.weight(19.9), "light")
			-- fallSpeed exactly 30: land_light (not nil); kills < -> <= and 30 -> 31 on line 83
			check.equal(Rules.landSound(30), "land_light")
			-- fallSpeed exactly 60: land_heavy; kills >= -> > and 60 -> 61 on line 86
			check.equal(Rules.landSound(60), "land_heavy")
		end)
		test.case("every sound the rules can ask for is made by the footsteps set", function()
			if not fs.isFile("assets/sounds/sets/footsteps.json") then
				return -- (the footsteps set is a project's sound set: the kit's own repo has none)
			end
			local set = serde.decode("json", fs.readFile("assets/sounds/sets/footsteps.json"))
			local made: { [string]: boolean } = {}
			local mx = set.matrix
			for weapon in mx.weapons do
				for surface in mx.surfaces do
					for _, w in { "light", "heavy" } do
						made[`{weapon}_{mx.verb}_{surface}_{w}`] = true
					end
				end
			end
			for name, m in set.members do
				if m.weights and #m.weights == 2 then
					made[name .. "_light"], made[name .. "_heavy"] = true, true
				else
					made[name] = true
				end
			end
			for mat in Rules.SURFACE do
				for _, speed in { 16, 24 } do
					local n = Rules.stepSound(mat, speed) :: string
					check.is_true(made[n] == true)
				end
			end
			check.is_true(made[Rules.stepSound("Neon", 16) :: string] == true)
			-- the surfaces games remap to (SampleRegion's gold meadow) are made too
			check.is_true(made.boot_step_drygrass_light == true and made.boot_step_drygrass_heavy == true)
			check.is_true(made.land_light and made.land_heavy and made.cloth_rustle)
		end)
	end)
end
