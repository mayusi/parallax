-- movesrefs.spec.luau (kit) — a move is where the lanes meet by NAME (its animation, its sound events, its effects):
-- `kit move` names every one nothing answers to, so a moveset is never silent in game because one lane's piece is
-- missing or misspelled. The probe is built from the pieces the project it runs in really has: the kit's own repo, a
-- new project (its starter effects) and a grown game all get a true answer.
local fs = require("@lune/fs")
local serde = require("@lune/serde")

local frk = require("../frk")
local test, check = frk.test, frk.check

local Config = require("../../lib/config")
local MovesCmd = require("../../cmd/moves")

-- the first piece of a kind this project HAS (sorted, so the pick is stable): a clip or preset file's stem, nil if none
local function firstStem(dir: string): string?
	if not fs.isDir(dir) then
		return nil
	end
	local stems = {}
	for _, f in fs.readDir(dir) do
		local stem = string.match(f, "^([%w_]+)%.json$")
		if stem and string.sub(stem, 1, 1) ~= "_" and fs.isFile(`{dir}/{f}`) then
			table.insert(stems, stem)
		end
	end
	table.sort(stems)
	return stems[1]
end

-- the first sound event the project's catalog names, nil if it names none
local function firstEvent(): string?
	local ok, d = pcall(function()
		return serde.decode("json", fs.readFile("assets/sounds/_events.json"))
	end)
	if not ok or type(d) ~= "table" or type(d.events) ~= "table" then
		return nil
	end
	local names = {}
	for name in d.events do
		table.insert(names, name)
	end
	table.sort(names)
	return names[1]
end

return function()
	-- the pieces below live at the project ROOT: pin the root, whatever game games/.active names (a lane's
	-- `kit game use SampleGame` turned both cases red: the probe was looked up in that game's runtime)
	Config.setGame("none")
	test.suite("moves: every animation, sound and effect a move names exists", function()
		test.case("a move whose pieces all exist has nothing missing", function()
			local anim, event, effect = firstStem("assets/animations"), firstEvent(), firstStem("assets/effects")
			if not (anim or event or effect) then
				return -- (no game pieces of any kind here: the kit's own repo)
			end
			local move = {
				name = "Probe",
				anim = anim,
				sfx = if event then { { frame = 2, event = event } } else nil,
				onHit = { sfx = event, vfx = effect },
			}
			check.equal(#MovesCmd.missingReferences(move), 0)
		end)

		test.case("each missing or misspelled piece is named with the lane that makes it", function()
			local move = {
				name = "Probe",
				anim = "NoSuchClip",
				sfx = { { frame = 2, event = "NoSuchWhoosh" } },
				vfx = { { frame = 4, preset = "no_such_slash" } },
				onHit = { sfx = "NoSuchImpactSound", vfx = "hit_sparkz", reaction = "NoSuchReaction" },
			}
			local missing = MovesCmd.missingReferences(move)
			local all = table.concat(missing, "\n")
			check.equal(#missing, 6)
			check.truthy(string.find(all, 'animation "NoSuchClip"', 1, true))
			check.truthy(string.find(all, 'sound event "NoSuchWhoosh"', 1, true))
			check.truthy(string.find(all, 'sound event "NoSuchImpactSound"', 1, true))
			check.truthy(string.find(all, 'effect "no_such_slash"', 1, true))
			check.truthy(string.find(all, 'effect "hit_sparkz"', 1, true)) -- a typo is caught
			check.truthy(string.find(all, 'animation "NoSuchReaction"', 1, true))
			check.truthy(string.find(all, "the vfx lane", 1, true))
		end)
	end)
end
