-- animupper.spec.luau — THE UPPER-BODY VERSION of a move (the owner's method lists, 2026-11-14: animation masking): a
-- move that says "upper" is also built with its legs left out (kit/cmd/anim.luau AnimCmd.upperClip, in every build),
-- and the game plays that version while the character is moving (src/kit/MovesRules.clipFor, called by src/kit/Moves)
-- so the walk keeps the legs under the attack. A move that asks and cannot have one is refused with the reason.
local frk = require("../frk")
local fs = require("@lune/fs")
local serde = require("@lune/serde")
local test, check = frk.test, frk.check

local Anim = require("../../lib/anim")
local AnimCmd = require("../../cmd/anim")
local MovesRules = require("../../../src/kit/MovesRules")

-- a made-up R6 move as a keyframe spec: the torso and an arm turn, the legs step
local function spec(extra: { [string]: any }?): any
	local s: { [string]: any } = {
		name = "SpecSlash",
		rig = "R6",
		fps = 30,
		keys = {
			{
				t = 0,
				pose = {
					Torso = { 0, 0, 0 },
					["Right Arm"] = { 0, 0, 0 },
					["Left Leg"] = { 0, 0, 0 },
					["Right Leg"] = { 0, 0, 0 },
				},
			},
			{
				t = 0.5,
				pose = {
					Torso = { 0, 8, 0 },
					["Right Arm"] = { 90, 0, 0 },
					["Left Leg"] = { 20, 0, 0 },
					["Right Leg"] = { -20, 0, 0 },
				},
			},
		},
		events = { { name = "Hit", t = 0.4 } },
		upper = true,
	}
	for k, v in extra or {} do
		s[k] = v
	end
	return s
end

-- the move as the build has it: the spec compiled (an R15 clip) and folded to R6, the ask carried over
local function made(extra: { [string]: any }?): any
	local clip = Anim.clipFromSpec(spec(extra), {})
	local r6 = Anim.foldToR6(clip :: any)
	r6.upper = (clip :: any).upper
	return r6
end

return function()
	test.suite("the upper-body version of a move: the build", function()
		test.case("the ask rides on the clip; the version is the same clip with its legs left out", function()
			local clip = made()
			check.truthy(clip ~= nil and clip.upper == true and clip.joints["Left Leg"] ~= nil)
			local up, why = AnimCmd.upperClip(clip)
			check.truthy(up ~= nil and why == nil)
			check.equal(up.name, "SpecSlashUpper")
			check.equal(up.mask, "upper")
			check.truthy(up.joints["Left Leg"] == nil and up.joints["Right Leg"] == nil)
			check.truthy(up.joints.Torso == clip.joints.Torso and up.joints["Right Arm"] == clip.joints["Right Arm"]) -- the very same motion
			check.truthy(up.upper == nil and up.match == nil and up.root == nil and up.warp == nil)
			check.truthy(#up.times == #clip.times and up.events == clip.events) -- its length and its Hit are the move's
			-- the move itself is untouched
			check.truthy(clip.joints["Left Leg"] ~= nil and clip.name == "SpecSlash" and clip.mask == nil)
		end)
		test.case("the model the game plays keys the body above the hips and no leg", function()
			local up = AnimCmd.upperClip(made())
			local model, _, issues = Anim.modelFromClip(up, "R6")
			for _, issue in issues do
				check.truthy(issue.severity ~= "error")
			end
			local text = serde.encode("json", model)
			check.truthy(
				string.find(text, '"Torso"', 1, true) ~= nil and string.find(text, '"Right Arm"', 1, true) ~= nil
			)
			check.truthy(
				string.find(text, '"Left Leg"', 1, true) == nil and string.find(text, '"Right Leg"', 1, true) == nil
			)
			local whole = serde.encode("json", (Anim.modelFromClip(made(), "R6")))
			check.truthy(string.find(whole, '"Left Leg"', 1, true) ~= nil) -- (the move itself does key them)
		end)
		test.case("a move that asks and cannot have one is refused, with the reason", function()
			local travels = made()
			travels.root = {}
			for i = 0, #travels.times - 1 do
				table.insert(travels.root, { 0, 0, 0, 1, 0, 0, -0.2 * i })
			end
			local _, why1 = AnimCmd.upperClip(travels)
			check.truthy(string.find(why1 :: string, "cannot be played over the walk", 1, true) ~= nil)
			local still = made()
			still.root = { { 0, 0, 0, 1, 0, 0, 0 }, { 0, 0, 0, 1, 0, 0, -0.03 } } -- a root that does not really travel
			check.truthy(AnimCmd.upperClip(still) ~= nil)
			-- R6 has no waist: a torso that turns or drops would carry the walking legs
			local twist = made()
			local n = #twist.joints.Torso.frames
			local h = math.rad(40) / 2
			twist.joints.Torso.frames[n] = { 0, math.sin(h), 0, math.cos(h), 0, 0, 0 }
			local _, whyT = AnimCmd.upperClip(twist)
			check.truthy(string.find(whyT :: string, "R6 has no waist", 1, true) ~= nil)
			check.truthy(string.find(whyT :: string, "turns 40 degrees", 1, true) ~= nil)
			local drop = made()
			local last = table.clone(drop.joints.Torso.frames[n])
			last[6] -= 0.5
			drop.joints.Torso.frames[n] = last
			local _, whyD = AnimCmd.upperClip(drop)
			check.truthy(string.find(whyD :: string, "moves 0.50 studs", 1, true) ~= nil)
			local masked = made()
			masked.mask = "upper"
			local _, why2 = AnimCmd.upperClip(masked)
			check.truthy(string.find(why2 :: string, "an upper-body move already", 1, true) ~= nil)
			local legless = made()
			legless.joints["Left Leg"], legless.joints["Right Leg"] = nil, nil
			local _, why3 = AnimCmd.upperClip(legless)
			check.truthy(string.find(why3 :: string, "keys no leg", 1, true) ~= nil)
			local r15 = made()
			r15.rig = "R15"
			local _, why4 = AnimCmd.upperClip(r15)
			check.truthy(string.find(why4 :: string, "made of an R6 clip", 1, true) ~= nil)
			for _, ask in { "yes" :: any, 1 } do
				local c = made()
				c.upper = ask
				local up, why = AnimCmd.upperClip(c)
				check.truthy(up == nil and string.find(why :: string, '"upper" is true', 1, true) ~= nil)
			end
			local plain = made({ upper = false })
			check.truthy(plain.upper == false) -- (said no: the build makes no version and no error)
		end)
		test.case(
			"the build still makes it, names it in the move's metadata and fails on a move that cannot have it",
			function()
				local build = fs.readFile("kit/cmd/anim.luau")
				for _, line in
					{
						"local up, why = AnimCmd.upperClip(r6)",
						"metas[src.name].upper = upName",
						"if (clip :: any).upper ~= nil and (clip :: any).upper ~= false then",
						"for _, src in AnimCmd.sources(nil) do",
						"meta.camera, meta.camera_kick = nil, nil",
						'it asks for an upper-body version ("upper") and cannot have one',
						"meta.root, meta.fps, meta.warp, meta.match, meta.additive, meta.upper = nil, nil, nil, nil, nil, nil",
					}
				do
					check.truthy(string.find(build, line, 1, true) ~= nil)
				end
				-- the version never joins the build's `names` (those need a clip file for strips, gates and looks)
				check.truthy(string.find(build, "table.insert(names, upName)", 1, true) == nil)
				-- the legs the build leaves out are the legs the strike builder's own mask leaves out
				local strike = fs.readFile("kit/anim/strike.py")
				check.truthy(string.find(strike, 'for leg in ("Right Leg", "Left Leg"):', 1, true) ~= nil)
				check.truthy(
					#AnimCmd.LEGS == 2
						and table.find(AnimCmd.LEGS, "Right Leg") ~= nil
						and table.find(AnimCmd.LEGS, "Left Leg") ~= nil
				)
			end
		)
	end)

	test.suite("the upper-body version of a move: the game", function()
		local meta = {
			Slash = { duration = 0.5, upper = "SlashUpper" },
			SlashUpper = { duration = 0.5, mask = "upper" },
			Stab = { duration = 0.4 },
			Broken = { duration = 0.4, upper = "Gone" }, -- its version is not in the game
		}
		test.case("moving, a move with a version plays it; standing, the move itself", function()
			check.equal(MovesRules.clipFor("Slash", meta, true), "SlashUpper")
			check.equal(MovesRules.clipFor("Slash", meta, false), "Slash")
		end)
		test.case("a move with no version, or whose version is missing, plays itself", function()
			check.equal(MovesRules.clipFor("Stab", meta, true), "Stab")
			check.equal(MovesRules.clipFor("Broken", meta, true), "Broken")
			check.equal(MovesRules.clipFor("Unknown", meta, true), "Unknown")
			check.equal(MovesRules.clipFor("Slash", nil, true), "Slash")
			check.equal(MovesRules.clipFor("Slash", { Slash = { upper = 5 } }, true), "Slash")
			check.equal(MovesRules.clipFor("SlashUpper", meta, true), "SlashUpper") -- the version has no version
		end)
		test.case("the game still asks, with whether the character is being moved", function()
			local moves = fs.readFile("src/kit/Moves.luau")
			check.truthy(
				string.find(
					moves,
					"hum.RigType == Enum.HumanoidRigType.R6 and Anim.going(hum).Magnitude > MovesRules.MOVING",
					1,
					true
				) ~= nil
			)
			check.truthy(string.find(moves, "Anim.play(hum, clipName,", 1, true) ~= nil)
			check.truthy(MovesRules.MOVING > 0 and MovesRules.MOVING < 1)
		end)
	end)
end
