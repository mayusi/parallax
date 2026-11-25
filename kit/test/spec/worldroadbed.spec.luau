-- worldroadbed.spec.luau (kit) — A ROAD'S BED CUT INTO AND FILLED ONTO THE LAND (src/kit/RoadBed.luau; the owner's
-- finding W-R07). ONE RULE for the game (it writes the land's voxels by it), the compiler (it sets everything down on
-- that land) and kit world check (it walks the heights the compiler samples through the same rule).
-- The tables below were worked out by a second, separate writing of the rule (Python, kept with the kit's scratch
-- tools: build/scratch/gen_roadbed2.py wrote this file): the nearest point found by looking at EVERY stretch (the
-- rule's own index looks at a few), the bed's line by looking from every point at every other (the rule's own makes
-- two passes) - so a slip in one of the two shows.
-- Not claimed here: how a cutting looks in the game. That is the land, written and looked at.
local frk = require("../frk")
local test, check = frk.test, frk.check

local RoadBed = require("../../../src/kit/RoadBed")

local BEDS: { any } = {
	{ points = { { -60, 10, 0 }, { 0, 10, 0 }, { 40, 18, 30 }, { 40, 18, 90 } }, width = 8, shoulder = 12 },
	{ points = { { -20, 14, -50 }, { -20, 14, 70 } }, width = 6, shoulder = 6 },
	{
		points = { { -180, 4, -100 }, { -100, 12, -100 }, { -90, 13, -90 }, { -100, 14, -80 }, { -180, 22, -80 } },
		width = 6,
		shoulder = 12,
	},
	{ points = { { 110, 0, -40 }, { 110, 8, 40 }, { 90, 8, 40 }, { 90, 16, -40 } }, width = 6, shoulder = 12 },
}
local TABLE = {
	{ -60, 0, 10.0 },
	{ 0, 0, 10.0 },
	{ -30, 0, 10.0 },
	{ -30, 4, 10.0 },
	{ -30, 10, 10.1 },
	{ -30, 16, 10.02 },
	{ -30, 16.01, 10.0197 },
	{ -30, -9.5, 10.343551071 },
	{ 20, 15, 14.0 },
	{ 40, 60, 18.0 },
	{ 46, 60, 17.592592593 },
	{ 52, 60, 14.148148148 },
	{ 60, 60, 13.2 },
	{ -20, 0, 14.0 },
	{ -20, 3, 14.0 },
	{ -23, 0, 14.0 },
	{ -29, 0, 10.0 },
	{ -20, 71, 14.0 },
	{ -20, 80, 8.6 },
	{ -70, 0, 9.25 },
	{ -80, 0, 8.0 },
	{ 200, 200, 16.0 },
	{ 40, 91, 18.0 },
	{ 40, 100, 14.5 },
	{ 10, 7.5, 12.0 },
	{ -132, -92, 8.559259259 },
	{ -132, -90, 8.363310185 },
	{ -132, -88, 13.754398148 },
	{ -140, -95, 7.988888889 },
	{ -150, -85, 18.114814815 },
	{ -95, -90, 12.733767943 },
	{ -88, -90, 13.0 },
	{ -170, -110, 6.122916667 },
	{ -170, -70, 11.392824074 },
	{ -100, -90, 11.751867045 },
	{ -120, -90.001, 9.189181332 },
	{ 100, 0, 12.109953704 },
	{ 100, 20, 12.487962963 },
	{ 100, -20, 11.731944444 },
	{ 100, 39, 8.0 },
	{ -102.57, -85.3, 13.793047101 },
	{ -14.25, -103.34, 14.3877 },
	{ -45.31, -35.89, 10.8112 },
	{ -174.34, -3.29, 3.3817 },
	{ -179.88, -20.26, 3.6138 },
	{ -171.14, -99.14, 4.886 },
	{ -75.38, 70.18, 6.1256 },
	{ -156.57, -68.66, 9.216232525 },
}
-- each road's bed, sample by sample: { x, z, height }
local PROFILES: { [string]: { { number } } } = {
	ridge = {
		{ -200.0, 0.0, 2.1875 },
		{ -192.0, 0.0, 2.5875 },
		{ -184.0, 0.0, 2.9875 },
		{ -176.0, 0.0, 3.3875 },
		{ -168.0, 0.0, 3.7875 },
		{ -160.0, 0.0, 4.1875 },
		{ -152.0, 0.0, 4.5875 },
		{ -144.0, 0.0, 4.9875 },
		{ -136.0, 0.0, 5.3875 },
		{ -128.0, 0.0, 5.7875 },
		{ -120.0, 0.0, 6.1875 },
		{ -112.0, 0.0, 6.5875 },
		{ -104.0, 0.0, 6.9875 },
		{ -96.0, 0.0, 7.3875 },
		{ -88.0, 0.0, 7.7875 },
		{ -80.0, 0.0, 8.1875 },
		{ -72.0, 0.0, 8.5875 },
		{ -64.0, 0.0, 8.9875 },
		{ -56.0, 0.0, 9.434375 },
		{ -48.0, 0.0, 10.1625 },
		{ -40.0, 0.0, 10.9625 },
		{ -32.0, 0.0, 11.7625 },
		{ -24.0, 0.0, 12.5625 },
		{ -16.0, 0.0, 13.3625 },
		{ -8.0, 0.0, 14.1625 },
		{ 0.0, 0.0, 14.9625 },
		{ 8.0, 0.0, 14.1625 },
		{ 16.0, 0.0, 13.3625 },
		{ 24.0, 0.0, 12.5625 },
		{ 32.0, 0.0, 11.7625 },
		{ 40.0, 0.0, 10.9625 },
		{ 48.0, 0.0, 10.1625 },
		{ 56.0, 0.0, 9.434375 },
		{ 64.0, 0.0, 8.9875 },
		{ 72.0, 0.0, 8.5875 },
		{ 80.0, 0.0, 8.1875 },
		{ 88.0, 0.0, 7.7875 },
		{ 96.0, 0.0, 7.3875 },
		{ 104.0, 0.0, 6.9875 },
		{ 112.0, 0.0, 6.5875 },
		{ 120.0, 0.0, 6.1875 },
		{ 128.0, 0.0, 5.7875 },
		{ 136.0, 0.0, 5.3875 },
		{ 144.0, 0.0, 4.9875 },
		{ 152.0, 0.0, 4.5875 },
		{ 160.0, 0.0, 4.1875 },
		{ 168.0, 0.0, 3.7875 },
		{ 176.0, 0.0, 3.3875 },
		{ 184.0, 0.0, 2.9875 },
		{ 192.0, 0.0, 2.5875 },
		{ 200.0, 0.0, 2.1875 },
	},
	falling = {
		{ -50.0, 0.0, 33.1953125 },
		{ -42.0, 0.0, 32.7953125 },
		{ -34.0, 0.0, 32.3953125 },
		{ -26.0, 0.0, 31.9953125 },
		{ -18.0, 0.0, 31.571875 },
		{ -10.0, 0.0, 31.0 },
		{ -2.0, 0.0, 30.2 },
		{ 6.0, 0.0, 29.4 },
		{ 14.0, 0.0, 28.6 },
		{ 22.0, 0.0, 27.8 },
		{ 30.0, 0.0, 27.0 },
		{ 38.0, 0.0, 26.2 },
		{ 46.0, 0.0, 25.4 },
		{ 54.0, 0.0, 24.6 },
		{ 62.0, 0.0, 23.8 },
		{ 70.0, 0.0, 23.0 },
		{ 78.0, 0.0, 22.2 },
		{ 86.0, 0.0, 21.4 },
		{ 94.0, 0.0, 20.6 },
		{ 102.0, 0.0, 19.8 },
		{ 110.0, 0.0, 19.0 },
		{ 118.0, 0.0, 18.428125 },
		{ 126.0, 0.0, 18.0046875 },
		{ 134.0, 0.0, 17.6046875 },
		{ 142.0, 0.0, 17.2046875 },
		{ 150.0, 0.0, 16.8046875 },
	},
	loop = {
		{ -120.0, -120.0, 3.070933534 },
		{ -112.0, -120.0, 2.934181279 },
		{ -104.0, -120.0, 2.774181279 },
		{ -96.0, -120.0, 2.614181279 },
		{ -88.0, -120.0, 2.454181279 },
		{ -80.0, -120.0, 2.294181279 },
		{ -72.0, -120.0, 2.134181279 },
		{ -64.0, -120.0, 1.974181279 },
		{ -56.0, -120.0, 1.814181279 },
		{ -48.0, -120.0, 1.654181279 },
		{ -40.0, -120.0, 1.494181279 },
		{ -32.0, -120.0, 1.345270927 },
		{ -24.0, -120.0, 1.345270927 },
		{ -16.0, -120.0, 1.345270927 },
		{ -8.0, -120.0, 1.345270927 },
		{ 0.0, -120.0, 1.345270927 },
		{ 8.0, -120.0, 1.345270927 },
		{ 16.0, -120.0, 1.345270927 },
		{ 24.0, -120.0, 1.345270927 },
		{ 32.0, -120.0, 1.345270927 },
		{ 40.0, -120.0, 1.270558228 },
		{ 48.0, -120.0, 1.110558228 },
		{ 56.0, -120.0, 0.950558228 },
		{ 64.0, -120.0, 0.790558228 },
		{ 72.0, -120.0, 0.630558228 },
		{ 80.0, -120.0, 0.470558228 },
		{ 88.0, -120.0, 0.310558228 },
		{ 96.0, -120.0, 0.150558228 },
		{ 104.0, -120.0, -0.009441772 },
		{ 112.0, -120.0, -0.169441772 },
		{ 120.0, -120.0, -0.329441772 },
		{ 120.0, -112.0, -0.489441772 },
		{ 120.0, -104.0, -0.649441772 },
		{ 120.0, -96.0, -0.809441772 },
		{ 120.0, -88.0, -0.969441772 },
		{ 120.0, -80.0, -1.129441772 },
		{ 120.0, -72.0, -1.289441772 },
		{ 120.0, -64.0, -1.449441772 },
		{ 120.0, -56.0, -1.609441772 },
		{ 120.0, -48.0, -1.624245741 },
		{ 120.0, -40.0, -1.624245741 },
		{ 120.0, -32.0, -1.624245741 },
		{ 120.0, -24.0, -1.624245741 },
		{ 120.0, -16.0, -1.624245741 },
		{ 120.0, -8.0, -1.624245741 },
		{ 120.0, 0.0, -1.624245741 },
		{ 120.0, 8.0, -1.624245741 },
		{ 120.0, 16.0, -1.624245741 },
		{ 120.0, 24.0, -1.624245741 },
		{ 120.0, 32.0, -1.624245741 },
		{ 120.0, 40.0, -1.624245741 },
		{ 120.0, 48.0, -1.624245741 },
		{ 120.0, 56.0, -1.609441772 },
		{ 120.0, 64.0, -1.449441772 },
		{ 120.0, 72.0, -1.289441772 },
		{ 120.0, 80.0, -1.129441772 },
		{ 120.0, 88.0, -0.969441772 },
		{ 120.0, 96.0, -0.809441772 },
		{ 120.0, 104.0, -0.649441772 },
		{ 120.0, 112.0, -0.489441772 },
		{ 120.0, 120.0, -0.329441772 },
		{ 112.0, 120.0, -0.169441772 },
		{ 104.0, 120.0, -0.009441772 },
		{ 96.0, 120.0, 0.150558228 },
		{ 88.0, 120.0, 0.310558228 },
		{ 80.0, 120.0, 0.470558228 },
		{ 72.0, 120.0, 0.630558228 },
		{ 64.0, 120.0, 0.790558228 },
		{ 56.0, 120.0, 0.950558228 },
		{ 48.0, 120.0, 1.110558228 },
		{ 40.0, 120.0, 1.270558228 },
		{ 32.0, 120.0, 1.345270927 },
		{ 24.0, 120.0, 1.345270927 },
		{ 16.0, 120.0, 1.345270927 },
		{ 8.0, 120.0, 1.345270927 },
		{ 0.0, 120.0, 1.345270927 },
		{ -8.0, 120.0, 1.345270927 },
		{ -16.0, 120.0, 1.345270927 },
		{ -24.0, 120.0, 1.345270927 },
		{ -32.0, 120.0, 1.345270927 },
		{ -40.0, 120.0, 1.494181279 },
		{ -48.0, 120.0, 1.654181279 },
		{ -56.0, 120.0, 1.814181279 },
		{ -64.0, 120.0, 1.974181279 },
		{ -72.0, 120.0, 2.134181279 },
		{ -80.0, 120.0, 2.294181279 },
		{ -88.0, 120.0, 2.454181279 },
		{ -96.0, 120.0, 2.614181279 },
		{ -104.0, 120.0, 2.774181279 },
		{ -112.0, 120.0, 2.934181279 },
		{ -120.0, 120.0, 3.070933534 },
		{ -120.0, 112.0, 3.199128019 },
		{ -120.0, 104.0, 3.214134036 },
		{ -120.0, 96.0, 3.214134036 },
		{ -120.0, 88.0, 3.214134036 },
		{ -120.0, 80.0, 3.214134036 },
		{ -120.0, 72.0, 3.214134036 },
		{ -120.0, 64.0, 3.214134036 },
		{ -120.0, 56.0, 3.214134036 },
		{ -120.0, 48.0, 3.299635067 },
		{ -120.0, 40.0, 3.459635067 },
		{ -120.0, 32.0, 3.619635067 },
		{ -120.0, 24.0, 3.779635067 },
		{ -120.0, 16.0, 3.939635067 },
		{ -120.0, 8.0, 4.099635067 },
		{ -120.0, 0.0, 4.259635067 },
		{ -120.0, -8.0, 4.099635067 },
		{ -120.0, -16.0, 3.939635067 },
		{ -120.0, -24.0, 3.779635067 },
		{ -120.0, -32.0, 3.619635067 },
		{ -120.0, -40.0, 3.459635067 },
		{ -120.0, -48.0, 3.299635067 },
		{ -120.0, -56.0, 3.214134036 },
		{ -120.0, -64.0, 3.214134036 },
		{ -120.0, -72.0, 3.214134036 },
		{ -120.0, -80.0, 3.214134036 },
		{ -120.0, -88.0, 3.214134036 },
		{ -120.0, -96.0, 3.214134036 },
		{ -120.0, -104.0, 3.214134036 },
		{ -120.0, -112.0, 3.199128019 },
	},
	bend = {
		{ 0.0, 0.0, 2.662666958 },
		{ 7.5, 0.0, 2.662666958 },
		{ 15.0, 0.0, 2.662666958 },
		{ 22.5, 0.0, 2.662666958 },
		{ 30.0, 0.0, 2.662666958 },
		{ 37.5, 0.0, 2.56795818 },
		{ 45.0, 0.0, 2.194773495 },
		{ 52.5, 0.0, 1.819773495 },
		{ 60.0, 0.0, 1.444773495 },
		{ 60.0, 5.0, 1.194773495 },
		{ 65.714285714, 10.0, 0.81512543 },
		{ 71.428571429, 15.0, 0.435477366 },
		{ 77.142857143, 20.0, 0.055829301 },
		{ 82.857142857, 25.0, -0.323818764 },
		{ 88.571428571, 30.0, -0.703466829 },
		{ 94.285714286, 35.0, -1.083114893 },
		{ 100.0, 40.0, -1.462762958 },
	},
}

local function land(x: number, z: number): number
	return 12 + 0.05 * x - 0.03 * z
end

local function near(a: number, b: number, tolerance: number?): boolean
	return math.abs(a - b) < (tolerance or 1e-7)
end

-- the stored (kept short) bed's height above a place on its line
local function onLine(points: { { number } }, x: number, z: number): number?
	local best, bestY = math.huge, nil
	for k = 1, #points - 1 do
		local a, b = points[k], points[k + 1]
		local vx, vz = b[1] - a[1], b[3] - a[3]
		local len2 = vx * vx + vz * vz
		local t = if len2 > 0 then math.clamp(((x - a[1]) * vx + (z - a[3]) * vz) / len2, 0, 1) else 0
		local d = (x - a[1] - vx * t) ^ 2 + (z - a[3] - vz * t) ^ 2
		if d < best then
			best, bestY = d, a[2] + (b[2] - a[2]) * t
		end
	end
	return if best < 0.01 then bestY else nil
end

local function ridge(x: number, _z: number): number
	return 30 * math.max(0, 1 - math.abs(x) / 40)
end
local function falling(x: number, _z: number): number
	return 50 - 50 * math.clamp(x / 100, 0, 1)
end
local function wavy(x: number, z: number): number
	return 6 * math.sin(x / 23) + 4 * math.cos(z / 17)
end
local LINES = {
	ridge = { { { -200, 0 }, { 200, 0 } }, ridge, 0.1 },
	falling = { { { -50, 0 }, { 150, 0 } }, falling, 0.1 },
	loop = { { { -120, -120 }, { 120, -120 }, { 120, 120 }, { -120, 120 }, { -120, -120 } }, wavy, 0.02 },
	bend = { { { 0, 0 }, { 60, 0 }, { 60, 5 }, { 100, 40 } }, wavy, 0.05 },
}

return function()
	test.suite("A road's bed cut into and filled onto the land", function()
		test.case("the one table: the rule's index finds what looking at every stretch finds", function()
			check.equal(#TABLE, 48)
			for _, row in TABLE do
				local got = RoadBed.apply(BEDS, row[1], row[2], land(row[1], row[2]))
				check.truthy(near(got, row[3]), `at {row[1]}, {row[2]}: {got} against {row[3]}`)
			end
			-- on a grid round the hairpin (where a piece of a long bed once answered for its neighbour's leg): the
			-- index against a bed made of the same points with no index of its own - a fresh table each time
			for x = -200, -70, 3.7 do
				for z = -125, -55, 3.1 do
					local fresh = { points = table.clone(BEDS[3].points), width = 6, shoulder = 12 }
					local y1 = RoadBed.at(BEDS[3], x, z)
					local y2 = RoadBed.at(fresh, x, z)
					check.equal(y1, y2)
				end
			end
		end)

		test.case("by hand", function()
			local one = { BEDS[1] }
			check.truthy(near(RoadBed.apply(one, -30, 0, 99), 10)) -- (cut)
			check.truthy(near(RoadBed.apply(one, -30, 3.9, -50), 10)) -- (filled)
			check.truthy(near(RoadBed.apply(one, 40, 60, 0), 18))
			check.truthy(near(RoadBed.at(one[1], 20, 15) :: number, 14))
			check.truthy(near(RoadBed.apply(one, -30, 10, 30), 20)) -- (the middle of the shoulder)
			local _, share = RoadBed.at(one[1], -30, 10)
			check.equal(share, 0.5)
			check.equal(RoadBed.apply(one, -30, 16, 30), 30)
			check.equal(RoadBed.apply(one, -30, 40, 30), 30)
			check.equal(RoadBed.at(one[1], -30, 16), nil)
			check.truthy(near(RoadBed.apply(one, -64, 0, 30), 10))
			local past = RoadBed.apply(one, -70, 0, 30)
			check.truthy(past > 10 and past < 30)
			check.equal(RoadBed.apply(one, -77, 0, 30), 30)
			check.truthy(near(RoadBed.apply(BEDS, -20, 0, 30), 14)) -- (the later bed, at its own level)
			check.truthy(near(RoadBed.apply({ BEDS[2], BEDS[1] }, -20, 0, 30), 10))
			-- a tie: halfway between two legs, the FIRST stretch's height (the later leg lies west, in the cells looked
			-- at first)
			check.truthy(near(RoadBed.at(BEDS[4], 100, 0) :: number, 4))
			check.truthy(near(RoadBed.at(BEDS[4], 100, -20) :: number, 2))
			check.equal(RoadBed.apply(nil, 1, 2, 3.5), 3.5)
			check.equal(RoadBed.apply({}, 1, 2, 3.5), 3.5)
			-- far from every stretch nothing is looked at, and nothing is changed
			check.equal(RoadBed.at(one[1], 5000, -5000), nil)
		end)

		test.case("a bed's line: of all lines that hold the grade, the one of the least worst cut or fill", function()
			for name, case in LINES do
				local made = RoadBed.profile(case[1], case[2], case[3], nil, 3) :: any
				local want = PROFILES[name]
				-- every sample worked out by looking from every point at every other lies on the stored line
				for _, s in want do
					local y = onLine(made.points, s[1], s[2])
					check.truthy(
						y ~= nil and near(y :: number, s[3], 0.052),
						`{name} at {s[1]}, {s[2]}: {y} against {s[3]}`
					)
				end
				-- a point it keeps is a sample's own, to the thousandth its numbers are kept to
				for _, p in made.points do
					local found = false
					for _, s in want do
						if near(p[1], s[1], 0.0006) and near(p[3], s[2], 0.0006) then
							found = true
							check.truthy(near(p[2], s[3], 0.0006), `{name}: {p[2]} against {s[3]}`)
						end
					end
					check.truthy(found or name == "loop", `{name}: a point of no sample at {p[1]}, {p[3]}`)
				end
				-- it holds the grade (to the thousandth its numbers are kept to)
				check.truthy(
					RoadBed.steepest(made.points) <= case[3] + 0.003,
					`{name}: {RoadBed.steepest(made.points)}`
				)
				-- and it is short: a straight run at one grade is two points
				check.truthy(#made.points <= #want + 1)
			end
			-- the reader's road: land falling 50 studs over 100, the road 200 long at 0.1 - the misfit is SHARED by
			-- both ends (a forward pass alone left a 33-stud embankment at the end and nothing at the start)
			local f = RoadBed.profile(LINES.falling[1], falling, 0.1) :: any
			local startFill = f.points[1][2] - falling(-50, 0)
			local endFill = f.points[#f.points][2] - falling(150, 0)
			check.truthy(startFill < -10 and endFill > 10, `start {startFill}, end {endFill}`)
			check.truthy(near(-startFill, endFill, 0.01))
			check.truthy(near(f.cut, f.fill, 0.01))
			-- the same road walked the other way is the same bed
			local back = RoadBed.profile({ { 150, 0 }, { -50, 0 } }, falling, 0.1) :: any
			check.truthy(near(back.points[1][2], f.points[#f.points][2], 0.002))
			check.truthy(near(back.cut, f.cut, 0.01) and near(back.fill, f.fill, 0.01))
			-- a loop closes at its own height: no step where it began
			local loop = RoadBed.profile(LINES.loop[1], wavy, 0.02) :: any
			check.equal(loop.loop, true)
			check.equal(loop.points[1][2], loop.points[#loop.points][2])
			check.equal(loop.points[1][1], loop.points[#loop.points][1])
			check.truthy(RoadBed.steepest(loop.points) <= 0.02 + 0.003)
			-- a road that only touches its start again at a corner is no loop: three points
			check.equal((RoadBed.profile({ { 0, 0 }, { 50, 0 }, { 0, 0 } }, wavy, 0.1) :: any).loop, false)
			-- cut and fill are read at the road's edges too: along a side slope the line itself is neither cut nor
			-- filled, and the edges are
			local side = RoadBed.profile({ { -100, 0 }, { 100, 0 } }, function(_x: number, z: number): number
				return 0.6 * z
			end, 0.1, nil, 11) :: any
			check.truthy(near(side.cut, 6.6, 1e-6) and near(side.fill, 6.6, 1e-6), `{side.cut} {side.fill}`)
			local centre = RoadBed.profile({ { -100, 0 }, { 100, 0 } }, function(_x: number, z: number): number
				return 0.6 * z
			end, 0.1) :: any
			check.equal(centre.cut, 0)
			-- on level land the bed is the land, and a straight road is its two ends
			local flat = RoadBed.profile({ { 0, 0 }, { 50, 0 }, { 50, 70 } }, function(): number
				return 7
			end, 0.2) :: any
			check.equal(flat.cut, 0)
			check.equal(flat.fill, 0)
			check.equal(flat.length, 120)
			check.equal(#flat.points, 3) -- (its two ends and its corner)
			check.equal(`{flat.points[2][1]} {flat.points[2][3]}`, "50 0")
			for _, p in flat.points do
				check.equal(p[2], 7)
			end
			-- a point typed twice is one point
			local twice = RoadBed.profile({ { 0, 0 }, { 0, 0 }, { 40, 0 } }, function(): number
				return 3
			end, 0.2) :: any
			check.equal(twice.length, 40)
			check.equal(#twice.points, 2)
			-- one point's bump is no hill: the land's line is eased before it is held to the grade
			local spike = RoadBed.profile({ { 0, 0 }, { 80, 0 } }, function(x: number): number
				return if x == 40 then 10 else 0
			end, 5) :: any
			local top = onLine(spike.points, 40, 0) :: number
			check.truthy(top < 4 and top > 1, `the spike's top is {top}`)
			check.truthy(spike.cut > 6)
			-- a road that leaves the land has no bed, and says where
			local none, why = RoadBed.profile({ { 0, 0 }, { 96, 0 } }, function(x: number): number?
				return if x > 60 then nil else 0
			end, 0.2)
			check.equal(none, nil)
			check.truthy(string.find(why :: string, "the road leaves the land at [64, 0]", 1, true))
			local short, whyShort = RoadBed.profile({ { 5, 5 } }, ridge, 0.2)
			check.equal(short, nil)
			check.truthy(string.find(whyShort :: string, "of some length", 1, true))
			-- the steepest stretch, rising or falling
			check.equal(RoadBed.steepest({ { 0, 10, 0 }, { 10, 5, 0 } }), 0.5)
			check.equal(RoadBed.steepest({ { 0, 0, 0 }, { 10, 2, 0 }, { 20, 2, 0 } }), 0.2)
		end)

		test.case("what is no bed", function()
			check.equal(#RoadBed.problems({ points = { { 0, 0, 0 }, { 8, 0, 0 } }, width = 8, shoulder = 10 }), 0)
			check.equal(#RoadBed.problems({ points = { { 0, 0, 0 }, { 8, 0, 0 } }, width = 64, shoulder = 64 }), 0)
			check.equal(#RoadBed.problems({ points = { { 0, 0, 0 }, { 8, 0, 0 } }, width = 2, shoulder = 2 }), 0)
			for _, bad in
				{
					"road",
					{ points = { { 0, 0, 0 } }, width = 8, shoulder = 10 },
					{ points = { { 0, 0 }, { 8, 0 } }, width = 8, shoulder = 10 },
					{ points = { { 0, 0, 0 }, { 8, 0 / 0, 0 } }, width = 8, shoulder = 10 },
					{ points = { { 0, 0, 0 }, { 8, 0, 0 } }, width = 1, shoulder = 10 },
					{ points = { { 0, 0, 0 }, { 8, 0, 0 } }, width = 65, shoulder = 10 },
					{ points = { { 0, 0, 0 }, { 8, 0, 0 } }, width = 8, shoulder = 1 },
					{ points = { { 0, 0, 0 }, { 8, 0, 0 } }, width = 8, shoulder = 65 },
					{ points = { { 0, 0, 0 }, { 8, 0, 0 } }, width = 8 },
				} :: { any }
			do
				check.equal(#RoadBed.problems(bad), 1)
			end
		end)
	end)
end
