-- review.spec.luau (kit) — the review page's rules (kit/lib/review.luau, kit/lib/localpage.luau; the 3D studio-route
-- plan, H8): a stage's state is the lock's own comparison, a click becomes the kit's own command and nothing else,
-- for what the page showed; and a local page writes only for the page that was served.
local fs = require("@lune/fs")
local process = require("@lune/process")

local frk = require("../frk")
local test, check = frk.test, frk.check

local ChartPlan = require("../../lib/chartplan")
local Config = require("../../lib/config")
local LaneLocks = require("../../lib/lanelocks")
local LocalPage = require("../../lib/localpage")
local Locks = require("../../lib/locks")
local Review = require("../../lib/review")
local truthy = require("../../lib/pytruth")

local PIC = { { path = "build/x.png", label = "x" } }

local function same(a: { string }, b: { string }): boolean
	if #a ~= #b then
		return false
	end
	for i, v in a do
		if b[i] ~= v then
			return false
		end
	end
	return true
end

local function has(text: string, needle: string): boolean
	return string.find(text, needle, 1, true) ~= nil
end

return function()
	test.suite("Review (one piece's stages, the owner's approvals in one place)", function()
		test.case("an artefact's state is the lock's own comparison: missing, waiting, approved, changed", function()
			local missing = Review.stageOf(
				"sheet",
				"The model sheet",
				{ ok = false, why = "no model sheet yet" },
				nil,
				"lune run kit sheet gun",
				{}
			)
			check.equal(missing.state, "missing")
			check.equal(missing.says, "no model sheet yet")
			check.equal(missing.make, "lune run kit sheet gun")
			check.equal(#missing.actions, 0) -- nothing true to show him yet: nothing to approve

			local waiting = Review.stageOf("sheet", "The model sheet", { ok = true, id = "a1" }, nil, nil, PIC)
			check.equal(waiting.state, "waiting")
			check.is_true(same(waiting.actions, { "approve", "redo" }))

			local yes = { by = "owner", words = "yes, this one", date = "2026-11-12", id = "a1" }
			local approved = Review.stageOf("sheet", "The model sheet", { ok = true, id = "a1" }, yes, nil, PIC)
			check.equal(approved.state, "approved")
			check.equal((approved.record :: any).words, "yes, this one")
			check.is_true(same(approved.actions, { "redo" })) -- an approval is not asked for twice

			-- the sheet was redrawn after his yes: his record is for another id
			local changed = Review.stageOf("sheet", "The model sheet", { ok = true, id = "b2" }, yes, nil, PIC)
			check.equal(changed.state, "changed")
			check.is_true(same(changed.actions, { "approve", "redo" }))
		end)

		test.case("a file a stage names but the page cannot show is counted, never dropped without a word", function()
			-- "drawn" is the hash of EVERY file the tool names: one that is left out of the page is one he never saw
			local files, shown, hidden = LaneLocks.showable(
				{ "beat0_pair.png", "beat1_pair.png" },
				{ "build/vfx/animatic/fire_side.mp4", "build/vfx/dailies/fire_animatic/beat0_page.png" }
			)
			check.is_true(same(files, { "beat0_pair.png", "beat1_pair.png" }))
			check.equal(#shown, 2)
			check.equal(hidden, 0)
			local _, kept, left = LaneLocks.showable(nil, {
				"build/vfx/animatic/fire_side.mp4",
				"build/vfx/animatic/fi re_side.mp4", -- a name the page's address rule does not take
				"build/vfx/animatic/../../../board/locks.json",
				"assets/effects/fire.png", -- outside the project's build/vfx
				"build/vfx//animatic/fire_side.mp4",
				"build/vfx/animatic/fire.plan.json", -- not a picture or a video
				12,
			})
			check.is_true(same(kept, { "build/vfx/animatic/fire_side.mp4" }))
			check.equal(left, 6)
			local plain, _, odd = LaneLocks.showable({ "beat0_pair.png", "../x.png", "a/b.png", "beat0_pair.jpg" }, nil)
			check.is_true(same(plain, { "beat0_pair.png" }))
			check.equal(odd, 3)
			local none, nothing, zero = LaneLocks.showable(nil, "not a list")
			check.equal(#none + #nothing + zero, 0)
		end)

		test.case("with a game active the stage's pictures are the GAME's build/vfx (card t6rx)", function()
			-- the stage tools write Config.build("vfx"): games/<Name>/build/vfx with a game active. The lock took only
			-- the project's build/vfx, so a game's animatic could never be shown, nor approved
			local game = "_SpecT6rxGame"
			local dir = `{Config.GAMES}/{game}`
			fs.writeDir(dir)
			local ok, err = pcall(function()
				Config.setGame(game)
				local _, kept, left = LaneLocks.showable(nil, {
					`games/{game}/build/vfx/animatic/fire_side.mp4`,
					"build/vfx/animatic/fire_side.mp4", -- the project's, not this game's
					`games/{game}/build/vfx/../../x.png`,
				})
				check.is_true(same(kept, { `games/{game}/build/vfx/animatic/fire_side.mp4` }))
				check.equal(left, 2)
			end)
			Config.setGame("none")
			fs.removeDir(dir)
			if not ok then
				error(err, 0)
			end
			local _, root = LaneLocks.showable(nil, { "build/vfx/animatic/fire_side.mp4" })
			check.equal(#root, 1)
		end)

		test.case("a yes is for the PICTURES he saw, where the artefact names them (a style sheet)", function()
			-- the same preset recorded again and its sheet drawn again: the same id, other pictures
			local first = { ok = true, id = "s1", drawn = "p1" }
			local again = { ok = true, id = "s1", drawn = "p2" }
			local yes = { by = "owner", words = "these read", date = "2026-11-12", id = "s1", drawn = "p1" }
			check.is_true(LaneLocks.holds(yes, first))
			check.is_false(LaneLocks.holds(yes, again))
			check.is_false(LaneLocks.holds(yes, { ok = true, id = "s2", drawn = "p1" })) -- another preset
			-- a record that names no pictures cannot say which he saw ...
			check.is_false(LaneLocks.holds({ by = "owner", words = "y", id = "s1" }, first))
			-- ... and an artefact that names none (a model sheet: its id is of its own picture) is held by its id
			check.is_true(LaneLocks.holds({ by = "owner", words = "y", id = "a1" }, { ok = true, id = "a1" }))
			check.is_false(LaneLocks.holds(nil, first))

			local shown = Review.stageOf("style", "The style sheet", first, yes, nil, PIC)
			check.equal(shown.state, "approved")
			local redrawn = Review.stageOf("style", "The style sheet", again, yes, nil, PIC)
			check.equal(redrawn.state, "changed")
			check.is_true(has(redrawn.says, "drawn again since you approved it"))
			check.is_true(same(redrawn.actions, { "approve", "redo" }))
			-- what the page showed is the id AND the pictures: a click for the old pictures is refused
			check.is_true(has(shown.seen :: string, "style:s1:p1|"))
			check.is_true(has(redrawn.seen :: string, "style:s1:p2|"))
			check.is_false(Review.fresh(redrawn, "approve", shown.seen))
			-- the command is told the part it can read again itself: the id and the pictures' hash
			check.equal(redrawn.expect, "style:s1:p2")
			-- ... and a click also names the picture FILES as they were (the same sheet written again is another look)
			local here = Review.stageOf("style", "The style sheet", again, nil, nil, PIC)
			local moved = Review.stageOf(
				"style",
				"The style sheet",
				again,
				nil,
				nil,
				{ { path = "kit/VERSION", label = "another file" } }
			)
			check.equal(here.expect, moved.expect)
			check.is_false(Review.fresh(moved, "approve", here.seen))
			local unnamed =
				Review.stageOf("style", "The style sheet", first, { by = "owner", words = "y", id = "s1" }, nil, PIC)
			check.equal(unnamed.state, "changed")
			check.is_true(has(unnamed.says, "does not say which pictures"))
		end)

		test.case("a step he waived is shown as waived: the build lock does not ask for it", function()
			local waiver =
				{ by = "owner", words = "skip the sheet on this one", date = "2026-11-10", steps = { "sheet" } }
			local waived = Review.stageOf(
				"sheet",
				"The model sheet",
				{ ok = false, why = "no model sheet yet" },
				nil,
				nil,
				{},
				waiver
			)
			check.equal(waived.state, "waived")
			check.equal((waived.record :: any).words, "skip the sheet on this one")
			check.equal(#waived.actions, 0) -- nothing drawn: nothing to approve, and nothing is asked
		end)

		test.case("an approval is for what the page SHOWED: a stage redrawn meanwhile refuses the click", function()
			local shown = Review.stageOf("sheet", "The model sheet", { ok = true, id = "a1" }, nil, nil, PIC)
			local redrawn = Review.stageOf("sheet", "The model sheet", { ok = true, id = "b2" }, nil, nil, PIC)
			check.is_true(Review.fresh(shown, "approve", shown.seen))
			check.is_false(Review.fresh(redrawn, "approve", shown.seen)) -- he saw a1; b2 is there now
			check.is_false(Review.fresh(redrawn, "approve", nil)) -- a click that does not say what it saw
			check.is_false(Review.fresh(redrawn, "verdict", shown.seen))
			check.is_true(Review.fresh(redrawn, "redo", nil)) -- a note about what he saw is still his note
		end)

		test.case("a chart's plan is the text the chart tool writes, read with Python's idea of true", function()
			local chart = {
				duration = 3.4,
				beats = {
					{ beat = "0 ignition", t = 0, len = 0.3, hold = 0, key = false },
					{ beat = "1 key", t = 0.3, len = 0.4, hold = 0.12, key = true },
				},
			}
			check.equal(Review.chartPlan(chart), "3.40|0.00,0.30,0.00,0;0.30,0.40,0.12,1")
			-- a hand-edited "key": 0 or "" is NOT the key beat (Luau alone would call both true, and the chart would
			-- read "changed" right after every approval)
			chart.beats[2].key = 0 :: any
			check.equal(Review.chartPlan(chart), "3.40|0.00,0.30,0.00,0;0.30,0.40,0.12,0")
			chart.beats[2].key = "" :: any
			check.equal(Review.chartPlan(chart), "3.40|0.00,0.30,0.00,0;0.30,0.40,0.12,0")
			check.is_true(truthy(1) and truthy("x") and truthy(true) and truthy({ 1 }))
			check.is_false(truthy(0) or truthy("") or truthy(false) or truthy(nil) or truthy({}))
		end)

		test.case("the scene gate and the page read a chart's plan with ONE function", function()
			check.equal(Review.chartPlan, ChartPlan)
			check.is_true(has(fs.readFile("kit/cmd/content.luau"), 'local chartPlanKey = require("../lib/chartplan")'))
			-- "beats" that is not a list (Python iterating an object sees its key names): no beat rows
			check.equal(ChartPlan({ duration = 2, beats = { a = { t = 1 } } }), "2.00|")
			check.equal(ChartPlan({}), "0.00|")
		end)

		test.case("a beat chart, by the scene gate's own rule", function()
			local chart: any = { duration = 1, beats = { { t = 0, len = 0.5, hold = 0, key = true } } }
			-- (the picture on this machine shows the chart's plan as it is now, unless a case says otherwise)
			local function own(more: any?): any
				local o: any = { drawnPlan = Review.chartPlan(chart), where = "fx/refs_measured" }
				for k, v in more or {} do
					o[k] = v
				end
				return o
			end
			check.equal(Review.chartStage("fire", nil, {}).state, "missing")
			check.equal(Review.chartStage("fire", chart, {}, own()).state, "missing") -- (no picture drawn: nothing to look at)
			local waiting = Review.chartStage("fire", chart, PIC, own())
			check.equal(waiting.state, "waiting")
			check.is_true(same(waiting.actions, { "approve", "redo" }))
			check.equal(waiting.expect, "1.00|0.00,0.50,0.00,1")
			check.equal(waiting.where, "fx/refs_measured")

			-- the picture is of ANOTHER plan (the chart was edited after it was drawn), or nobody wrote down of which
			-- (drawn before the kit kept that): nothing he can say yes to until it is drawn again
			local earlier = Review.chartStage("fire", chart, PIC, own({ drawnPlan = "1.00|0.00,0.20,0.00,1" }))
			check.equal(earlier.state, "missing")
			check.equal(#earlier.actions, 0)
			check.is_true(has(earlier.says, "earlier plan"))
			local unknown = Review.chartStage("fire", chart, PIC, { where = "fx/refs_measured" })
			check.equal(#unknown.actions, 0)
			check.is_true(has(unknown.says, "not known"))
			-- what the page showed is the plan AND the picture's plan: a picture drawn again is another look
			check.is_false(Review.fresh(waiting, "approve", earlier.seen))
			-- the picture's file is one per set NAME: one drawn from another folder's set is not this chart's
			local other =
				Review.chartStage("fire", chart, PIC, own({ drawnWhere = "games/Other/assets/effects/refs_measured" }))
			check.equal(#other.actions, 0)
			check.is_true(has(other.says, "another folder's set of the same name"))
			check.equal(#Review.chartStage("fire", chart, PIC, own({ drawnWhere = "FX\\refs_measured" })).actions, 2)
			-- the picture he is asked to approve holds a test frame of the key beat, and its key beat is no guess
			local bare = Review.chartStage("fire", chart, PIC, own({ test = false, guessed = false }))
			check.equal(#bare.actions, 0)
			check.is_true(has(bare.says, "no test frame of the key beat"))
			local guess = Review.chartStage("fire", chart, PIC, own({ test = true, guessed = true }))
			check.equal(#guess.actions, 0)
			check.is_true(has(guess.says, "only guessed"))
			check.equal(#Review.chartStage("fire", chart, PIC, own({ test = true, guessed = false })).actions, 2)

			chart.approved =
				{ by = "owner", words = "Yes, build it", date = "2026-11-11", plan = Review.chartPlan(chart) }
			local approved = Review.chartStage("fire", chart, PIC, own())
			check.equal(approved.state, "approved")
			check.equal(approved.ref, "fire")
			-- his yes stands when the picture is not drawn on this machine: it is said, and nothing is offered
			local undrawn = Review.chartStage("fire", chart, {}, own())
			check.equal(undrawn.state, "approved")
			check.is_true(has(undrawn.says, "not drawn on this machine"))
			check.equal(#undrawn.actions, 0)
			-- ... and an approved chart whose old picture has no plan written beside it is simply approved
			check.equal(Review.chartStage("fire", chart, PIC, { where = "x" }).says, "approved 2026-11-11")

			-- "owner" written by a session is not his record (the gate's Locks.isOwner reads "who" too)
			chart.approved.who = "claude@claude-code"
			local notHis = Review.chartStage("fire", chart, PIC, own())
			check.equal(notHis.state, "waiting")
			check.is_true(has(notHis.says, '"owner" by claude@claude-code'))
			check.is_false(Locks.isOwner(chart.approved))
			chart.approved.who = nil

			chart.beats[1].len = 0.9 -- re-timed after his yes
			check.equal(Review.chartStage("fire", chart, PIC, own()).state, "changed")

			-- a label an agent wrote onto charts he had not looked at is not his look ...
			chart.approved = { by = "owner blanket approval 2026-10-16", words = "all charts", date = "2026-10-16" }
			local label = Review.chartStage("fire", chart, PIC, own())
			check.equal(label.state, "waiting")
			check.is_true(has(label.says, "not your own look"))
			-- ... unless the piece was built before that rule (the gate's own list), or he approved the piece in the locks
			check.equal(Review.chartStage("fire", chart, PIC, own({ before = true })).state, "approved")
			check.equal(
				Review.chartStage("fire", chart, PIC, own({ approval = { by = "owner", words = "go" } })).state,
				"approved"
			)
			-- ... and a record that is no owner's at all is never his, built before the rule or not
			chart.approved = { by = "model-proposed", words = "looks right", date = "2026-11-12" }
			check.equal(Review.chartStage("fire", chart, PIC, own({ before = true })).state, "waiting")
			-- his waiver of the chart for this piece: the gate asks no chart
			local waived = Review.chartStage(
				"fire",
				nil,
				{},
				{ waiver = { by = "owner", words = "no chart", date = "d" } }
			)
			check.equal(waived.state, "waived")
		end)

		test.case("a click becomes the kit's own command, for the folder the page read", function()
			local sheet = Review.stageOf("sheet", "The model sheet", { ok = true, id = "a1" }, nil, nil, PIC)
			local cmd, args = Review.plan("3d", "gun", sheet, "approve", "  yes,\nthis one ", nil, nil)
			check.equal(cmd, "approve")
			-- (--expect: what the page showed - the command records nothing for anything else)
			check.is_true(same(args, {
				"3d",
				"gun",
				"yes, this one",
				"--by",
				"owner",
				"--stage",
				"sheet",
				"--via",
				Review.VIA,
				"--expect",
				"sheet:a1:",
			}))
			-- a fixture project's piece: the same folder the page read is the one the command reads
			local _, fixture = Review.plan("3d", "gun", sheet, "approve", "yes", nil, { models = "tmp/models" })
			check.is_true(same(fixture, {
				"3d",
				"gun",
				"yes",
				"--by",
				"owner",
				"--stage",
				"sheet",
				"--via",
				Review.VIA,
				"--expect",
				"sheet:a1:",
				"--models",
				"tmp/models",
			}))
			-- an effect's style sheet: the same record shape, in the effects folder the page read
			local style =
				Review.stageOf("style", "The style sheet", { ok = true, id = "s1", drawn = "p1" }, nil, nil, PIC)
			local scmd, sargs = Review.plan("vfx", "ember", style, "approve", "yes", nil, nil)
			check.equal(scmd, "approve")
			check.is_true(same(sargs, {
				"vfx",
				"ember",
				"yes",
				"--by",
				"owner",
				"--stage",
				"style",
				"--via",
				Review.VIA,
				"--expect",
				"style:s1:p1",
				"--effects",
				Config.path("vfx"),
			}))
			-- a fixture project's effect: the folder the page read is the one the command reads
			local _, fx = Review.plan("vfx", "ember", style, "approve", "yes", nil, { effects = "tmp/effects" })
			check.equal(fx[#fx - 1], "--effects")
			check.equal(fx[#fx], "tmp/effects")
			-- the timing animatic is a stage of the SET: recorded under the set's name, whichever piece's page showed it
			local animatic =
				Review.stageOf("animatic", "The timing animatic", { ok = true, id = "m1", drawn = "v1" }, nil, nil, PIC)
			animatic.ref = "fire"
			local acmd, aargs = Review.plan("vfx", "ember", animatic, "approve", "yes, this motion", nil, nil)
			check.equal(acmd, "approve")
			check.is_true(same(aargs, {
				"vfx",
				"fire",
				"yes, this motion",
				"--by",
				"owner",
				"--stage",
				"animatic",
				"--via",
				Review.VIA,
				"--expect",
				"animatic:m1:v1",
				"--effects",
				Config.path("vfx"),
			}))

			-- a chart: the plan he looked at, in the folder the page read it in
			local chart = Review.chartStage(
				"fire",
				{ duration = 1, beats = {} },
				PIC,
				{ drawnPlan = "1.00|", where = "fx/refs_measured" }
			)
			local ccmd, cargs = Review.plan("vfx", "ember", chart, "approve", "go", nil, nil)
			check.equal(ccmd, "vfx")
			check.is_true(same(cargs, {
				"chart",
				"fire",
				"--approve",
				"go",
				"--by",
				"owner",
				"--via",
				Review.VIA,
				"--expect-plan",
				"1.00|",
				"--measured",
				"fx/refs_measured",
			}))

			local rcmd, rargs = Review.plan("vfx", "ember", chart, "redo", "the arc should stay longer", nil, nil)
			check.equal(rcmd, "task")
			check.is_true(same(rargs, {
				"rework",
				"ember - The beat chart (fire): the arc should stay longer",
				"--area",
				"vfx",
				"--as",
				Review.WHO,
			}))
		end)

		test.case(
			"an approval is recorded in HIS words: a click with none is refused, the page invents none",
			function()
				local sheet = Review.stageOf("sheet", "The model sheet", { ok = true, id = "a1" }, nil, nil, PIC)
				local cmd, why = Review.plan("3d", "gun", sheet, "approve", "", nil, nil)
				check.equal(cmd, nil)
				check.is_true(has(why, "in your words"))
				check.equal((Review.plan("3d", "gun", sheet, "approve", "   ", nil, nil)), nil)
				check.equal((Review.plan("3d", "gun", sheet, "approve", "ok", nil, nil)), "approve") -- a plain yes is his word
			end
		)

		test.case("a verdict is a number, keep or redo, with his words and the picture he saw", function()
			local final: Review.Stage = {
				key = "final",
				title = "The finished piece: your verdict",
				state = "waiting",
				says = "built",
				pictures = PIC,
				actions = { "verdict", "redo" },
			}
			local cmd, args = Review.plan("vfx", "ember", final, "verdict", "the arc reads now", "8", nil)
			check.equal(cmd, "verdict")
			check.is_true(
				same(args, { "vfx", "ember", "8", "the arc reads now", "--shown", "build/x.png", "--as", Review.WHO })
			)
			local _, three = Review.plan("3d", "gun", final, "verdict", "flat", 3, { route = "typed sculpt forms" })
			check.is_true(same(three, {
				"asset",
				"gun",
				"3",
				"flat",
				"--shown",
				"build/x.png",
				"--route",
				"typed sculpt forms",
				"--as",
				Review.WHO,
			}))
			local _, keep = Review.plan("anim", "Roundhouse", final, "verdict", "calm, keep", "KEEP", nil)
			check.equal(keep[3], "keep")
			for _, bad in { "eleven", "11", "-1", "1e1", "0x0a", "inf", "" } do
				check.equal((Review.plan("vfx", "ember", final, "verdict", "good", bad, nil)), nil)
			end
			check.equal((Review.plan("vfx", "ember", final, "verdict", "", "8", nil)), nil) -- a number alone teaches nothing
		end)

		test.case(
			"what a stage does not offer, and words that are not words, are refused before any command",
			function()
				local approved = Review.stageOf(
					"sheet",
					"The model sheet",
					{ ok = true, id = "a1" },
					{ by = "owner", words = "y", date = "d", id = "a1" },
					nil,
					PIC
				)
				local cmd, why = Review.plan("3d", "gun", approved, "approve", "again", nil, nil)
				check.equal(cmd, nil)
				check.is_true(has(why, "nothing to approve here"))
				check.equal((Review.plan("3d", "gun", approved, "redo", "", nil, nil)), nil) -- a redo with no note says nothing
				-- a note that starts like a flag would be read as one by the command
				check.equal((Review.plan("3d", "gun", approved, "redo", "--by owner", nil, nil)), nil)
				check.equal((Review.plan("3d", "gun", approved, "delete", "x", nil, nil)), nil)
			end
		)

		test.case(
			"the page may fetch the pictures the stages name, and the typed line is what a person would type",
			function()
				local allowed = Review.allowed({
					Review.stageOf("sheet", "The model sheet", { ok = true, id = "a1" }, nil, nil, PIC),
					Review.stageOf("blockout", "The blockout", { ok = false, why = "none" }, nil, nil, {}),
				})
				check.equal(allowed["build/x.png"], true)
				check.equal(allowed["board/locks.json"], nil)
				check.equal(
					Review.typed("approve", { "3d", "gun", 'yes, "this" one', "--by", "owner" }),
					"lune run kit approve 3d gun \"yes, 'this' one\" --by owner"
				)
			end
		)

		test.case("what to watch includes the places a picture is not in YET", function()
			local watched = table.concat(Review.watch("vfx", "ember", nil), " ")
			check.is_true(has(watched, "build/vfx/dailies/ember"))
			check.is_true(has(watched, "build/vfx/stylesheet"))
			-- ... and the files that are rewritten in place (a folder's time does not move for those)
			check.is_true(has(watched, "build/vfx/stylesheet/ember.json"))
			check.is_true(has(watched, "build/vfx/animatic/ember.plan.json")) -- (no set declared: under its own name)
			check.is_true(has(watched, "build/vfx/dailies/ember/dailies.json"))
			-- ... and what a stage's state is read from besides: his verdicts, the list of pieces from before a rule
			check.is_true(has(watched, "kit/knowledge/vault/vfx/verdicts"))
			check.is_true(has(watched, "kit/vfx/scene_gate.json"))
			check.is_true(has(table.concat(Review.watch("3d", "gun", nil), " "), "kit/knowledge/vault/3d/verdicts"))
			local fx = table.concat(Review.watch("vfx", "ember", { effects = "tmp/effects" }), " ")
			check.is_true(has(fx, "tmp/effects/ember.json") and has(fx, "tmp/effects/refs_measured"))
			check.is_true(has(table.concat(Review.watch("3d", "gun", { models = "tmp/models" }), " "), "tmp/models"))
			check.equal(Review.modified("no/such/file.png"), "-")
		end)

		test.case("the page's 3D note is a general truth: it asks the build lock nothing", function()
			-- (the lock's own answer for a piece may WRITE its lists while it reads them: nothing on this page writes)
			local before = if fs.isFile(Locks.FILE) then fs.readFile(Locks.FILE) else ""
			local note = Review.note("3d", "a_piece_with_no_brief", {}, nil)
			check.is_true(has(note :: string, "only of a NEW complex, hero or aaa piece"))
			check.equal(Review.note("vfx", "ember", {}, nil), nil)
			check.equal(if fs.isFile(Locks.FILE) then fs.readFile(Locks.FILE) else "", before)
		end)

		test.case("a fixture's record is a plain file under build/, never the project's own however spelled", function()
			local root = (string.gsub(process.cwd, "[\\/]+$", ""))
			for _, refused in
				{
					"board/locks.json",
					"./board/locks.json",
					"BOARD\\locks.json",
					"build/../board/locks.json",
					root .. "/board/locks.json",
					root .. "\\board\\locks.json",
					-- one file has more spellings on Windows than a comparison can list: none of them is under build/
					"board/locks.json.",
					"board/locks.json ",
					"board/locks.json::$DATA",
					"board/LOCKS~1.JSO",
					-- ... and what IS under build/ must be spelled plainly
					"build/x/../../board/locks.json",
					"build/fixture/locks.json.",
					"build/fixture /locks.json",
					"build/fixture/locks.json::$DATA",
					"build/FIXTUR~1/locks.json",
					-- a record anywhere else in the project, or outside it, is no fixture's
					"kit/selftest/sheet/locks.json",
					"../elsewhere/build/locks.json",
					"C:/Windows/Temp/locks.json",
					-- plainly under build/, and its real place is still a file called board/locks.json: refused
					-- by where it leads (a folder under build/ can be a junction)
					"build/a_fixture/board/locks.json",
				}
			do
				check.is_true(Locks.useFixture(refused) ~= nil)
				check.equal(Locks.FILE, "board/locks.json") -- (a refusal changes nothing)
				check.is_false(Locks.fixture)
			end
		end)
	end)

	test.suite("LocalPage (what a page on 127.0.0.1 needs before it may write)", function()
		test.case("a local page is never shown inside another page's frame", function()
			local headers = LocalPage.pageHeaders("default-src 'self'")
			check.equal(headers["Content-Security-Policy"], "default-src 'self'; frame-ancestors 'none'")
			check.equal(headers["X-Frame-Options"], "DENY")
			check.equal(LocalPage.pageHeaders(nil)["Content-Security-Policy"], "frame-ancestors 'none'")
			for _, dest in { "iframe", "frame", "embed", "object", "fencedframe" } do
				check.is_true(LocalPage.framed({ ["sec-fetch-dest"] = dest }))
			end
			check.is_false(LocalPage.framed({ ["sec-fetch-dest"] = "document" }))
			check.is_false(LocalPage.framed({})) -- (a plain client says nothing of what the request is for)
		end)

		test.case("a part of a file is served when a part is asked for (a video is scrubbed by Range)", function()
			local function part(header: any, total: number): string
				local p = LocalPage.range(header, total)
				return `{p.status} {p.first}-{p.last}`
			end
			check.equal(part(nil, 1000), "200 0-999") -- no Range: the whole file
			check.equal(part("bytes=0-", 1000), "206 0-999") -- what a browser asks a video for first
			check.equal(part("bytes=0-1", 1000), "206 0-1")
			check.equal(part("bytes=500-599", 1000), "206 500-599")
			check.equal(part(" bytes = 990 - 5000 ", 1000), "206 990-999") -- past the end: up to the last byte
			check.equal(part("bytes=-100", 1000), "206 900-999") -- the last hundred
			check.equal(part("bytes=-5000", 1000), "206 0-999")
			check.equal(part("bytes=1000-", 1000), "416 0-999") -- starts past the end
			check.equal(part("bytes=-0", 1000), "416 0-999")
			check.equal(part("bytes=0-", 0), "416 0--1") -- an empty file has no part
			-- what this page does not serve is answered with the whole file (a server may): several ranges, another
			-- unit, a last byte before the first, words
			for _, header in { "bytes=0-1,5-9", "items=0-1", "bytes=9-2", "bytes=", "bytes=-", "bytes=a-b", "0-1" } do
				check.equal(part(header, 1000), "200 0-999")
			end
		end)

		test.case("the request must name this machine and this port exactly", function()
			check.is_true(LocalPage.hostOk({ host = "127.0.0.1:8791" }, 8791))
			check.is_true(LocalPage.hostOk({ host = "LOCALHOST:8791" }, 8791))
			check.is_true(LocalPage.hostOk({ host = "127.0.0.1" }, 8791))
			check.is_false(LocalPage.hostOk({ host = "127.0.0.1.evil.example" }, 8791)) -- a prefix is not a match
			check.is_false(LocalPage.hostOk({ host = "127.0.0.1:9999" }, 8791))
			check.is_false(LocalPage.hostOk({}, 8791))
		end)

		test.case("a write needs the page's token and comes from the page itself", function()
			local secret = "abc123"
			check.equal(LocalPage.writeProblem({ ["x-review-token"] = secret }, 8791, secret, "x-review-token"), nil)
			check.equal(
				LocalPage.writeProblem({
					["x-review-token"] = secret,
					origin = "http://127.0.0.1:8791",
					["sec-fetch-site"] = "same-origin",
				}, 8791, secret, "x-review-token"),
				nil
			)
			check.is_true(LocalPage.writeProblem({}, 8791, secret, "x-review-token") ~= nil)
			check.is_true(
				LocalPage.writeProblem({ ["x-review-token"] = "nope" }, 8791, secret, "x-review-token") ~= nil
			)
			check.is_true(
				LocalPage.writeProblem(
					{ ["x-review-token"] = secret, origin = "http://evil.example" },
					8791,
					secret,
					"x-review-token"
				) ~= nil
			)
			check.is_true(
				LocalPage.writeProblem(
					{ ["x-review-token"] = secret, ["sec-fetch-site"] = "cross-site" },
					8791,
					secret,
					"x-review-token"
				) ~= nil
			)
		end)
	end)
end
