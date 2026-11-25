-- worldcurve.luau — a smooth line THROUGH typed points (the owner's method list, 2026-11-13: "Spline-based roads",
-- "Spline-based rivers", "Spline-based paths", "Spline-based fences and walls"). Before this a road, a fence or a row
-- of posts ran straight from typed point to typed point: every bend was a hard corner.
--
-- The curve is a centripetal Catmull-Rom spline (Barry and Goldman's form; Yuksel, Schaefer and Keyser 2011 show why
-- the centripetal one: it passes through every typed point and makes no loop or cusp inside a span, which the
-- uniform one does when points stand unevenly). It is handed on as a POLYLINE: the generators already walk points,
-- so a curve is their points made many - cut so no joint turns more than `maxTurn` degrees and no piece is longer
-- than `step` studs. kit/world/curve.py is the same curve in Python (the terrain tool's rivers); the two are held to
-- one table of cases (kit/test/fixtures/curve_cases.json).
local Curve = {}

Curve.DEFAULTS = {
	step = 12, -- studs: the longest piece of a curve
	maxTurn = 6, -- degrees: what a joint is cut to turn, where the typed points leave room for it (see `least`)
	-- studs: no piece shorter than this. It is what LIMITS the turn of a joint on a tight bend: a curve through a
	-- right-angle corner typed with 40-stud legs turns about 9 degrees a piece at its tightest, with 10-stud legs 30
	-- (a fresh reader measured 17 and 59 when this was 2; the generators lap their pieces by each joint's own angle)
	least = 1,
	fine = 64, -- samples a span is walked in at least (a cut is always one of them: on the curve itself)
}
-- what an option may be asked down to (a blueprint cannot ask the compiler for a hundred thousand pieces)
Curve.FLOOR = { step = 0.5, least = 0.25, fine = 1024 }

local function dist(a: { number }, b: { number }): number
	local s = 0
	for i = 1, math.max(#a, #b) do
		local d = (b[i] or 0) - (a[i] or 0)
		s += d * d
	end
	return math.sqrt(s)
end

local function lerp(a: { number }, b: { number }, wa: number, wb: number): { number }
	local out = table.create(#a)
	for i = 1, #a do
		out[i] = a[i] * wa + (b[i] or 0) * wb
	end
	return out
end

-- the typed points with repeats dropped (a point typed twice has no direction to curve through)
function Curve.distinct(points: { { number } }): { { number } }
	local out: { { number } } = {}
	for _, p in points do
		if #out == 0 or dist(out[#out], p) > 1e-6 then
			table.insert(out, p)
		end
	end
	return out
end

-- one span p1 -> p2 of the centripetal spline through p0 p1 p2 p3, at u in 0..1
function Curve.span(p0: { number }, p1: { number }, p2: { number }, p3: { number }, u: number): { number }
	local t0 = 0
	local t1 = t0 + math.sqrt(dist(p0, p1))
	local t2 = t1 + math.sqrt(dist(p1, p2))
	local t3 = t2 + math.sqrt(dist(p2, p3))
	local t = t1 + (t2 - t1) * u
	local a1 = lerp(p0, p1, (t1 - t) / (t1 - t0), (t - t0) / (t1 - t0))
	local a2 = lerp(p1, p2, (t2 - t) / (t2 - t1), (t - t1) / (t2 - t1))
	local a3 = lerp(p2, p3, (t3 - t) / (t3 - t2), (t - t2) / (t3 - t2))
	local b1 = lerp(a1, a2, (t2 - t) / (t2 - t0), (t - t0) / (t2 - t0))
	local b2 = lerp(a2, a3, (t3 - t) / (t3 - t1), (t - t1) / (t3 - t1))
	return lerp(b1, b2, (t2 - t) / (t2 - t1), (t - t1) / (t2 - t1))
end

-- the angle (degrees) between the directions a -> b and b -> c
function Curve.turn(a: { number }, b: { number }, c: { number }): number
	local la, lb = dist(a, b), dist(b, c)
	if la < 1e-9 or lb < 1e-9 then
		return 0
	end
	local dot = 0
	for i = 1, math.max(#a, #b, #c) do
		dot += ((b[i] or 0) - (a[i] or 0)) * ((c[i] or 0) - (b[i] or 0))
	end
	return math.deg(math.acos(math.clamp(dot / (la * lb), -1, 1)))
end

-- the sharpest corner of a line of points, in degrees (0 = straight; what the design gate asks about)
function Curve.sharpest(points: { { number } }): number
	local pts = Curve.distinct(points)
	local worst = 0
	for i = 2, #pts - 1 do
		worst = math.max(worst, Curve.turn(pts[i - 1], pts[i], pts[i + 1]))
	end
	return worst
end

function Curve.length(points: { { number } }): number
	local total = 0
	for i = 2, #points do
		total += dist(points[i - 1], points[i])
	end
	return total
end

-- the smooth line through `points` as a polyline: every typed point is on it, in order; `closed`: it returns to its
-- first point (a ring road, a town wall). Two points, or one, are returned as they are: there is nothing to curve.
function Curve.through(points: { { number } }, opts: any?): { { number } }
	local o = opts or {}
	local step = if type(o.step) == "number" and o.step > 0 then o.step else Curve.DEFAULTS.step
	local maxTurn = if type(o.maxTurn) == "number" and o.maxTurn > 0 then o.maxTurn else Curve.DEFAULTS.maxTurn
	local least = if type(o.least) == "number" and o.least > 0 then o.least else Curve.DEFAULTS.least
	step = math.max(step, Curve.FLOOR.step)
	least = math.clamp(least, Curve.FLOOR.least, step / 2) -- (a least longer than the step would overrule it)
	local pts = Curve.distinct(points)
	local closed = o.closed == true
	if closed and #pts > 2 and dist(pts[1], pts[#pts]) <= 1e-6 then
		table.remove(pts) -- (typed with its first point again at the end)
	end
	if #pts < 3 then
		return pts
	end
	local n = #pts
	local function at(i: number): { number }
		if closed then
			return pts[(i - 1) % n + 1]
		elseif i < 1 then -- (an end has no neighbour: the curve leaves along the mirror of its first span)
			return lerp(pts[1], pts[2], 2, -1)
		elseif i > n then
			return lerp(pts[n], pts[n - 1], 2, -1)
		end
		return pts[i]
	end
	local out: { { number } } = { pts[1] }
	for i = 1, if closed then n else n - 1 do
		local p0, p1, p2, p3 = at(i - 1), at(i), at(i + 1), at(i + 2)
		-- walk the span in fine samples; cut where the line has turned `maxTurn` or run `step` since the last cut
		-- (never closer than `least` to the last cut or to the span's end, which is a typed point and always kept)
		-- (samples no farther apart than half the least piece: a long span is walked as finely as a short one)
		local fine = math.clamp(math.ceil(dist(p1, p2) / (least / 2)), Curve.DEFAULTS.fine, Curve.FLOOR.fine)
		local samples = table.create(fine + 1)
		for k = 0, fine do
			samples[k + 1] = Curve.span(p0, p1, p2, p3, k / fine)
		end
		local total = Curve.length(samples)
		local run, turned, walked = 0, 0, 0
		for k = 2, fine do
			local d = dist(samples[k - 1], samples[k])
			run += d
			walked += d
			turned += Curve.turn(samples[k - 1], samples[k], samples[k + 1])
			local dueTurn = turned >= maxTurn * 0.75
			-- (a cut may not fall within `least` of the span's end, so the last piece can run `least` over: cut early)
			local dueRun = run + dist(samples[k], samples[k + 1]) > math.max(step - least, least)
			if (dueTurn or dueRun) and run >= least and total - walked >= least then
				table.insert(out, samples[k])
				run, turned = 0, 0
			end
		end
		if not (closed and i == n) then
			table.insert(out, p2)
		end
	end
	if closed then
		table.insert(out, pts[1])
	end
	return out
end

return Curve
