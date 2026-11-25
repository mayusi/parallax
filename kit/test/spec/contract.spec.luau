-- contract.spec.luau (kit) — the cross-lane contract of a hero weapon (LIMITATIONS_FIXES_V4 §10 item 1 / §13.8 item 1;
-- kit/lib/contract.luau): a contract built from its sources passes, and every kind of drift - a model file's hash, a
-- hit frame moved, a socket lost, a sound event whose sound no recipe makes, a scale that is not 0.28, a move set or
-- VFX preset or PROMPT-X packet that changed - fails BY NAME. A null field needs its reason.
local serde = require("@lune/serde")

local frk = require("../frk")
local test, check = frk.test, frk.check

local Contract = require("../../lib/contract")

local function hash(s: string): string
	return serde.hash("sha256", s)
end

local function sha(tag: string): string
	return hash(tag)
end

-- a small hero's sources as kit/cmd/contract.luau reads them (every number is the sources', none typed in a contract)
local function inputs(over: ((any) -> ())?): any
	local inp = {
		hero = "fx_sword",
		madeWith = { model = "m/fx_sword.manifest.json", moves = "src/moves/FxSet.json", vfx = "fx_slash" },
		model = {
			asset = "fx_sword",
			manifestPath = "m/fx_sword.manifest.json",
			manifest = {
				asset = "fx_sword",
				anchors = { RightGrip = { 0, 0, 0.4 }, Tip = { 0, 0, -3 } },
				facts = { size_studs = { 0.3, 0.3, 3.5 } },
			},
			files = { ["m/fx_sword_blade.fbx"] = sha("blade v1"), ["m/fx_sword_color.png"] = sha("color v1") },
			mmPerStud = 280,
			mmPerStudSource = "kit default",
		},
		set = {
			path = "src/moves/FxSet.json",
			sha = sha("set v1"),
			data = {
				name = "FxSet",
				combo = { "FxCut1", "FxCut2" },
				parry = { anim = "FxParry" },
				moves = {
					FxCut1 = {
						anim = "FxCut1Clip",
						frames = { fps = 60, startup = 18, active = 4, recovery = 20 },
						cancel = { from = 23, to = 40, into = { "FxCut2" } },
						hitstop = 0.07,
						sfx = { { frame = 10, event = "FxSwing" } },
						onHit = { sfx = "FxHit" },
						vfx = { { frame = 17, preset = "fx_slash" } },
					},
					FxCut2 = {
						anim = "FxCut2Clip",
						frames = { fps = 60, startup = 20, active = 4, recovery = 24 },
						hitstop = 0.1,
						sfx = { { frame = 12, event = "FxSwing" } },
						onHit = { sfx = "FxHit" },
					},
				},
			},
		},
		moveFiles = {
			FxCut1 = { path = "assets/moves/FxCut1.json", sha = sha("cut1") },
			FxCut2 = { path = "assets/moves/FxCut2.json", sha = sha("cut2") },
		},
		clips = {
			FxCut1Clip = { files = { ["a/FxCut1Clip.move.json"] = sha("clip1") }, sword = { length = 3.6 } },
			FxCut2Clip = { files = { ["a/FxCut2Clip.move.json"] = sha("clip2") } },
			FxParry = { files = { ["a/FxParry.move.json"] = sha("parry") } },
		},
		vfx = { name = "fx_slash", kind = "preset", path = "e/fx_slash.json", sha = sha("slash v1") },
		cues = { fx_slash = { kind = "preset", path = "e/fx_slash.json", sha = sha("slash v1") } },
		sfx = {
			path = "s/_events.json",
			sha = sha("events v1"),
			events = {
				FxSwing = { sound = "fx_swing" },
				FxHit = { cases = { metal = { sounds = { ["0.5"] = "fx_hit_metal" } } }, switch = "surface" },
				FxParry = { sound = "fx_parry" },
			},
			made = { fx_swing = true, fx_hit_metal = true, fx_parry = true },
		},
		parryEvent = { event = "FxParry", source = "the runtime" },
		packet = { path = "p/abc.json", sha256 = sha("packet v1") },
	}
	if over then
		over(inp)
	end
	return inp
end

-- a stored contract: built, written as JSON and read back (nulls dropped, as from a real file)
local function stored(over: ((any) -> ())?): any
	return serde.decode("json", Contract.encode(Contract.build(inputs(over), hash)))
end

local function fresh(over: ((any) -> ())?): any
	return Contract.build(inputs(over), hash)
end

local function names(problems: { string }, needle: string): boolean
	for _, p in problems do
		if string.find(p, needle, 1, true) then
			return true
		end
	end
	return false
end

return function()
	test.suite("contract: a hero's lanes bound by one file, every drift caught by name (V4 §13.8 item 1)", function()
		test.case("a contract built from its sources passes, through a JSON round trip", function()
			local c = fresh()
			check.equal(#Contract.validate(c), 0)
			check.equal(#Contract.check(stored(), fresh()), 0)
			check.equal(c.studScale, 0.28)
			check.equal(c.movesTimeline.hitFrame, 18)
			check.equal(c.movesTimeline.cancelFrame, 23)
			check.equal(c.movesTimeline.hitstopFrames, 4) -- 0.07 s at 60 fps, rounded
			check.equal(c.movesTimeline.moves.FxCut2.hitstopFrames, 6)
			check.equal(c.sfxEvents.hit.sounds[1], "fx_hit_metal")
			check.equal(c.sfxEvents.parry.events[1], "FxParry")
			check.equal(c.sockets.RightGrip.pos[3], 0.4)
			check.equal(#c.modelSha256, 64)
		end)

		test.case("a field with no source is null WITH its reason, written as null, and still passes", function()
			local c = fresh()
			check.equal(c.sockets.Holster, Contract.NULL)
			check.truthy(c.whyNull["sockets.Holster"] ~= nil)
			check.truthy(c.whyNull["movesTimeline.moves.FxCut2.cancelFrame"] ~= nil) -- the last cut cancels into nothing
			check.truthy(c.whyNull.uiTrigger ~= nil)
			local text = Contract.encode(c)
			check.truthy(string.find(text, '"uiTrigger": null', 1, true) ~= nil)
			check.truthy(string.find(text, '"unmade": []', 1, true) ~= nil)
			local s = stored()
			s.whyNull.uiTrigger = nil
			check.truthy(names(Contract.validate(s), "uiTrigger: null with no reason"))
		end)

		test.case("a model file whose bytes changed: modelSha256 and the file, by name", function()
			local p = Contract.check(
				stored(),
				fresh(function(i)
					i.model.files["m/fx_sword_blade.fbx"] = sha("blade v2")
				end)
			)
			check.truthy(names(p, "drift modelSha256"))
			check.truthy(names(p, "model.files[m/fx_sword_blade.fbx]"))
		end)

		test.case("a hit frame moved by the anim lane: movesTimeline by name", function()
			local p = Contract.check(
				stored(),
				fresh(function(i)
					i.set.data.moves.FxCut1.frames.startup = 20
				end)
			)
			check.truthy(names(p, "drift movesTimeline.hitFrame: 18 -> 20"))
			check.truthy(names(p, "drift movesTimeline.moves.FxCut1.hitFrame: 18 -> 20"))
		end)

		test.case("a hitstop or cancel window changed: by name", function()
			local p = Contract.check(
				stored(),
				fresh(function(i)
					i.set.data.moves.FxCut1.hitstop = 0.12
					i.set.data.moves.FxCut1.cancel.from = 25
				end)
			)
			check.truthy(names(p, "drift movesTimeline.hitstopFrames: 4 -> 7"))
			check.truthy(names(p, "drift movesTimeline.cancelFrame: 23 -> 25"))
		end)

		test.case("a socket the 3D lane dropped: sockets.Tip by name", function()
			local p = Contract.check(
				stored(),
				fresh(function(i)
					i.model.manifest.anchors.Tip = nil
				end)
			)
			check.truthy(names(p, "drift sockets.Tip"))
		end)

		test.case("a sound event whose sound no recipe makes, and one gone from the catalogue", function()
			local p = Contract.check(
				stored(),
				fresh(function(i)
					i.sfx.made.fx_hit_metal = nil
					i.sfx.events.FxSwing = nil
				end)
			)
			check.truthy(names(p, "sfxEvents.hit: sound fx_hit_metal (FxHit) has no recipe or set that makes it"))
			check.truthy(names(p, "sfxEvents.swing: event FxSwing is not in the sound catalogue"))
		end)

		test.case(
			"a scale that is not 1 stud = 0.28 m: studScale, in the sources and in a hand-edited contract",
			function()
				check.truthy(names(
					Contract.check(
						stored(),
						fresh(function(i)
							i.model.mmPerStud = 300
						end)
					),
					"sources studScale: 0.3"
				))
				local s = stored()
				s.studScale = 0.3
				check.truthy(names(Contract.check(s, fresh()), "contract studScale: 0.3"))
			end
		)

		test.case("the move set, the VFX preset and the PROMPT-X packet: a changed hash is named", function()
			local p = Contract.check(
				stored(),
				fresh(function(i)
					i.set.sha = sha("set v2")
					i.cues.fx_slash.sha = sha("slash v2")
					i.vfx.sha = sha("slash v2")
					i.packet.sha256 = sha("packet v2")
				end)
			)
			check.truthy(names(p, "drift sources[src/moves/FxSet.json]"))
			check.truthy(names(p, "drift sources[e/fx_slash.json]"))
			check.truthy(names(p, "drift promptPacketSha256"))
		end)

		test.case("a lost source file and a hand-edited schema are refused", function()
			local p = Contract.check(
				stored(),
				fresh(function(i)
					i.model.files["m/fx_sword_color.png"] = Contract.MISSING
				end)
			)
			check.truthy(names(p, "model: m/fx_sword_color.png is missing"))
			local s = stored()
			s.schema = 2
			check.truthy(names(Contract.validate(s), "schema: 2"))
		end)

		test.case("a clip authored for another blade length is a warning, not a failure", function()
			check.equal(#Contract.warnings(fresh()), 0) -- 3.6 vs 3.5 studs: within a tenth
			local w = Contract.warnings(fresh(function(i)
				i.clips.FxCut1Clip.sword.length = 5
			end))
			check.truthy(names(w, "FxCut1Clip was authored for a 5-stud"))
		end)
	end)
end
