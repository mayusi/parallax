-- animsteer.spec.luau — STEERED motion matching, the game's side (the owner's limitations list, 2026-11-15, A-R02):
-- the cases a JSON query cannot carry to the game's matcher (numbers that are not numbers) and the rules the one
-- review asked for, on a made-up two-loop set with one move. The build's side and the two held to each other:
-- kit/test/python/test_anim_steering.py.
local frk = require("../frk")
local test, check = frk.test, frk.check

local AnimMatch = require("../../../src/kit/AnimMatch")

-- one joint; Idle stands (turn 0), Walk goes ahead at 8 (turned 0.2), Lunge does not loop and goes ahead at 30
local function q(a: number): { number }
	return { 0, math.sin(a / 2), 0, math.cos(a / 2), 0, 0, 0 }
end
local db: any = {
	joints = { "Torso" },
	rows = { q(0), q(0), q(0.2), q(0.2), q(0.4), q(0.4), q(0.4) },
	index = {
		{ "Idle", 0 },
		{ "Idle", 1 },
		{ "Walk", 0 },
		{ "Walk", 1 },
		{ "Lunge", 0 },
		{ "Lunge", 1 },
		{ "Lunge", 2 },
	},
	clips = {
		Idle = { first = 0, frames = 2, loop = true },
		Walk = { first = 2, frames = 2, loop = true },
		Lunge = { first = 4, frames = 3, loop = false },
	},
	traj = { { 0, 0, 0 }, { 0, 0, 0 }, { 0, -8, 0 }, { 0, -8, 0 }, { 0, -30, 0 }, { 0, -30, 0 }, { 0, -30, 0 } },
	traj_weight = 0.5,
	speed = 8,
	turn = 1,
	vel_weight = 0.05,
	stay = 0.05,
	fps = 30,
	rest = "Idle",
}
local STILL = { 0, 0, 0 }
local function pose(a: number): { number }
	return { 0, math.sin(a / 2), 0, math.cos(a / 2) }
end

return function()
	test.suite("steered motion matching: the game's side", function()
		test.case("where the player wants to go says nothing on numbers that are not numbers", function()
			for _, bad in
				{
					{ 0, -1, math.huge, 0, 16 },
					{ 0, -1, 0 / 0, 0, 16 },
					{ 0 / 0, -1, 0, -1, 16 },
					{ 0, -1, 0, -1, 0 / 0 },
					{ 0, -1, 0, 0, 16 },
				}
			do
				local w = AnimMatch.wanted(bad[1], bad[2], bad[3], bad[4], bad[5])
				check.truthy(w[1] == 0 and w[2] == 0 and w[3] == 0)
			end
			local w = AnimMatch.wanted(0, -1, 0, -1, 16)
			check.truthy(w[1] == 0 and w[2] == -16 and w[3] == 0)
		end)
		test.case("an ask that is not numbers is no ask: the search is the one that only continues motion", function()
			local plain = AnimMatch.motionNext(db, pose(0), STILL, { "Idle", 0 })
			for _, want in { { 0 / 0, -8, 0 }, { 0, math.huge, 0 }, { 0, -8, 0 / 0 } } do
				local got = AnimMatch.motionNext(db, pose(0), STILL, { "Idle", 0 }, want)
				check.truthy(got[1] == plain[1] and got[2] == plain[2])
			end
			check.equal(AnimMatch.motionNext(db, pose(0), STILL, { "Idle", 0 }, { 0, -8, 0 })[1], "Walk") -- (a real ask does steer)
			check.equal(AnimMatch.motionNext(db, pose(0), STILL, { "Idle", 0 }, { 0, -8 })[1], "Walk") -- (no turn given: none asked)
		end)
		test.case("a move in flight is not steered; steering never starts one unless the game names it", function()
			-- the lunge plays: whatever is asked, it goes on to its next frame
			for _, want in { { 0, 0, 0 }, { 0, -8, 0 }, { 0, 8, 0 } } do
				local got = AnimMatch.motionNext(db, pose(0.4), STILL, { "Lunge", 0 }, want)
				check.truthy(got[1] == "Lunge" and got[2] == 1)
			end
			-- standing, an ask that fits the lunge best (ahead, very fast) goes to the walk
			check.equal(AnimMatch.motionNext(db, pose(0), STILL, { "Idle", 0 }, { 0, -30, 0 })[1], "Walk")
			check.equal(
				AnimMatch.motionNext(
					db,
					pose(0),
					STILL,
					{ "Idle", 0 },
					{ 0, -30, 0 },
					{ Idle = true, Walk = true, Lunge = true }
				)[1],
				"Lunge"
			)
			-- with no ask the lunge is offered as it always was (a body pushed into its pose is sent to it)
			check.equal(AnimMatch.motionNext(db, pose(0.4), STILL, { "Idle", 0 })[1], "Lunge")
			-- an allowed map's false is not allowed
			check.equal(
				AnimMatch.motionNext(db, pose(0), STILL, { "Idle", 0 }, { 0, -8, 0 }, { Idle = true, Walk = false })[1],
				"Idle"
			)
		end)
	end)
end
