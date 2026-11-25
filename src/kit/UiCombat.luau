--!strict
-- UiCombat.luau — the COMBAT FEEDBACK KIT's rules (LIMITATIONS_FIXES_V4 UI-X 6.4 step 3 / 13.6), pure: no services, no
-- instances, so the kit's Lune specs run the very code the Ui runtime runs.
--
--   UiCombat.waypoint(lx, ly, lz, w, h, focal, margin, shape)  -> where an off-screen / waypoint marker sits
--   UiCombat.bearing(tx, tz, cx, cz, lookX, lookZ)             -> the attacker's bearing for a damage arc (deg)
--   UiCombat.limiter(max, window)                              -> a flash gate: at most `max` flashes a `window`
--   UiCombat.ladder(opts)                                      -> the hit / crit / kill streak ladder's state
--   UiCombat.compare(current, candidate, opts)                 -> a compare tooltip's lines (good / bad / same)
--
-- WAYPOINTS work in CAMERA SPACE (the camera looks down -Z; cam.CFrame:PointToObjectSpace(target)). A target in front
-- and inside the margin box is projected; anywhere else the marker pins to an inset ellipse (or rectangle) along the
-- direction (lx, -ly). That direction IS the projection's direction in front of the camera and its reflection behind
-- it (dot(toTarget, look) < 0), and it is continuous through the camera's own plane: a marker turning past the side of
-- the screen never jumps to the opposite edge, and a target level with the camera's plane (the projection divides by
-- ~0 there) still lands on the ellipse.
local UiCombat = {}

export type Waypoint = {
	x: number,
	y: number,
	onScreen: boolean,
	behind: boolean,
	angle: number, -- the arrow's rotation in degrees (0 = pointing up, clockwise)
	edge: string?, -- "left" | "right" | "top" | "bottom" while pinned
}

function UiCombat.waypoint(
	lx: number,
	ly: number,
	lz: number,
	w: number,
	h: number,
	focal: number,
	margin: number,
	shape: string?
): Waypoint
	local cx, cy = w / 2, h / 2
	local behind = lz >= 0
	if not behind then
		local depth = -lz
		local sx, sy = cx + focal * lx / depth, cy - focal * ly / depth
		if sx >= margin and sx <= w - margin and sy >= margin and sy <= h - margin then
			return { x = sx, y = sy, onScreen = true, behind = false, angle = 0, edge = nil }
		end
	end
	local dx, dy = lx, -ly
	local m = math.sqrt(dx * dx + dy * dy)
	if m < 1e-9 then
		-- straight behind (or on the camera itself): the bottom edge, where "behind you" reads
		dx, dy = 0, 1
	else
		dx, dy = dx / m, dy / m
	end
	local hx, hy = math.max(cx - margin, 1), math.max(cy - margin, 1)
	local k: number
	if shape == "rect" then
		k = math.min(hx / math.max(math.abs(dx), 1e-9), hy / math.max(math.abs(dy), 1e-9))
	else
		k = 1 / math.sqrt((dx / hx) ^ 2 + (dy / hy) ^ 2)
	end
	local edge = if math.abs(dx) * hy > math.abs(dy) * hx
		then (if dx > 0 then "right" else "left")
		else (if dy > 0 then "bottom" else "top")
	return {
		x = cx + dx * k,
		y = cy + dy * k,
		onScreen = false,
		behind = behind,
		angle = math.deg(math.atan2(dy, dx)) + 90,
		edge = edge,
	}
end

-- the bearing of a point (tx, tz) from the camera (cx, cz) against where it looks (lookX, lookZ), on the ground
-- plane: 0 = straight ahead (the top of the screen), +90 = to the right, +-180 = behind. A GuiObject's Rotation is
-- clockwise, so a damage arc drawn at the top takes Rotation = bearing. nil when either direction has no length.
function UiCombat.bearing(tx: number, tz: number, cx: number, cz: number, lookX: number, lookZ: number): number?
	local fx, fz = tx - cx, tz - cz
	local fm = math.sqrt(fx * fx + fz * fz)
	local lm = math.sqrt(lookX * lookX + lookZ * lookZ)
	if fm < 1e-6 or lm < 1e-6 then
		return nil
	end
	local ax, az = lookX / lm, lookZ / lm
	-- the camera's right on the ground: look (0, 0, -1) -> right (1, 0, 0)
	local rx, rz = -az, ax
	return math.deg(math.atan2((fx * rx + fz * rz) / fm, (fx * ax + fz * az) / fm))
end

-- WCAG 2.3.1 (three flashes): nothing on screen flashes more than `max` (3) times in any `window` (1 s). allow(t)
-- answers whether a NEW flash may start at time t (the caller keeps a refused one lit instead of strobing it).
export type Limiter = { max: number, window: number, times: { number }, allow: (Limiter, number) -> boolean }

local function allow(self: Limiter, t: number): boolean
	local keep: { number } = {}
	for _, s in self.times do
		if t - s < self.window then
			table.insert(keep, s)
		end
	end
	self.times = keep
	if #keep >= self.max then
		return false
	end
	table.insert(self.times, t)
	return true
end

function UiCombat.limiter(max: number?, window: number?): Limiter
	return { max = max or 3, window = window or 1, times = {}, allow = allow }
end

-- THE STREAK LADDER: hits and crits chain into a combo while each lands within `hitWindow` of the last; kills chain
-- into a multi-kill while each lands within `killWindow` (Halo's 4.5 s); "reset" (a death) clears both.
-- record(kind, t) -> an event: { kind, count, label, banner, rung }
--   kill: always a banner - the first is opts.killLabel ("Kill"), then rungs[count - 1] (rungs = the identity's own
--         words, e.g. {"Double", "Triple"}), past the last rung the last one with "x<count>"
--   crit: a banner ("Crit" + the combo); hit: a banner only on a combo milestone (every `hitStep` hits)
export type LadderEvent = { kind: string, count: number, label: string, banner: boolean, rung: number }
export type Ladder = {
	rungs: { string },
	hitWindow: number,
	killWindow: number,
	hitStep: number,
	killLabel: string,
	critLabel: string,
	hits: number,
	kills: number,
	lastHit: number,
	lastKill: number,
	record: (Ladder, string, number) -> LadderEvent?,
}

local function record(self: Ladder, kind: string, t: number): LadderEvent?
	if kind == "reset" then
		self.hits, self.kills = 0, 0
		self.lastHit, self.lastKill = -math.huge, -math.huge
		return nil
	end
	if kind == "hit" or kind == "crit" then
		if t - self.lastHit > self.hitWindow then
			self.hits = 0
		end
		self.hits += 1
		self.lastHit = t
		local n = self.hits
		if kind == "crit" then
			return { kind = "crit", count = n, label = `{self.critLabel} x{n}`, banner = true, rung = 0 }
		end
		local milestone = n % self.hitStep == 0
		return {
			kind = "hit",
			count = n,
			label = `x{n}`,
			banner = milestone,
			rung = if milestone then n // self.hitStep else 0,
		}
	end
	if kind == "kill" then
		if t - self.lastKill > self.killWindow then
			self.kills = 0
		end
		self.kills += 1
		self.lastKill = t
		local n = self.kills
		if n == 1 then
			return { kind = "kill", count = 1, label = self.killLabel, banner = true, rung = 0 }
		end
		local rungs = self.rungs
		if #rungs == 0 then
			return { kind = "kill", count = n, label = `{self.killLabel} x{n}`, banner = true, rung = n - 1 }
		end
		local label = if n - 1 <= #rungs then rungs[n - 1] else `{rungs[#rungs]} x{n}`
		return { kind = "kill", count = n, label = label, banner = true, rung = math.min(n - 1, #rungs) }
	end
	return nil
end

function UiCombat.ladder(opts: { [string]: any }?): Ladder
	local o: { [string]: any } = opts or {}
	local rungs: { string } = {}
	if type(o.rungs) == "table" then
		for _, r in o.rungs do
			if type(r) == "string" and r ~= "" then
				table.insert(rungs, r)
			end
		end
	end
	return {
		rungs = rungs,
		hitWindow = tonumber(o.hitWindow) or 2,
		killWindow = tonumber(o.killWindow) or 4.5,
		hitStep = math.max(2, math.floor(tonumber(o.hitStep) or 10)),
		killLabel = if type(o.killLabel) == "string" then o.killLabel else "Kill",
		critLabel = if type(o.critLabel) == "string" then o.critLabel else "Crit",
		hits = 0,
		kills = 0,
		lastHit = -math.huge,
		lastKill = -math.huge,
		record = record,
	}
end

-- COMPARE TOOLTIP: the candidate's stats against what is equipped. A stat missing on one side counts 0. Lower-is-
-- better stats (reload, weight, spread: opts.lowerBetter = {Reload = true}) turn a minus GOOD. opts.order fixes the
-- row order (else by name); opts.units = {Reload = "s"} adds a unit.
export type CompareRow = { stat: string, a: number, b: number, delta: number, text: string, tone: string }

local function fmt(v: number): string
	local r = math.floor(math.abs(v) * 100 + 0.5) / 100
	local s = if r == math.floor(r) then string.format("%d", r) else string.format("%.2f", r):gsub("0+$", "")
	return s
end

function UiCombat.compare(
	current: { [string]: number },
	candidate: { [string]: number },
	opts: { [string]: any }?
): { CompareRow }
	local o: { [string]: any } = opts or {}
	local lower: { [string]: boolean } = if type(o.lowerBetter) == "table" then o.lowerBetter else {}
	local units: { [string]: string } = if type(o.units) == "table" then o.units else {}
	local names: { string } = {}
	if type(o.order) == "table" then
		for _, n in o.order do
			table.insert(names, n)
		end
	else
		local seen: { [string]: boolean } = {}
		for n in current do
			seen[n] = true
		end
		for n in candidate do
			seen[n] = true
		end
		for n in seen do
			table.insert(names, n)
		end
		table.sort(names)
	end
	local rows: { CompareRow } = {}
	for _, n in names do
		local a, b = tonumber(current[n]) or 0, tonumber(candidate[n]) or 0
		local d = b - a
		local unit = if units[n] then units[n] else ""
		local tone = if math.abs(d) < 1e-9 then "same" elseif (d > 0) ~= (lower[n] == true) then "good" else "bad"
		local sign = if math.abs(d) < 1e-9 then "=" elseif d > 0 then "+" else "-"
		local text = if sign == "=" then `= {n}` else `{sign}{fmt(d)}{unit} {n}`
		table.insert(rows, { stat = n, a = a, b = b, delta = d, text = text, tone = tone })
	end
	return rows
end

-- the rows as a tooltip's Kit_TipLines ("good:+12 ATK\nbad:-3 DEF"): the tone rides in front, the runtime colours it
function UiCombat.tipLines(rows: { CompareRow }): string
	local out: { string } = {}
	for _, r in rows do
		table.insert(out, `{r.tone}:{r.text}`)
	end
	return table.concat(out, "\n")
end

-- one line of Kit_TipLines -> (tone, text): an explicit "good:" / "bad:" / "same:" prefix, else the old rule (a line
-- starting "+" is good, "-" bad)
function UiCombat.lineTone(line: string): (string, string)
	local tone, rest = string.match(line, "^(%a+):(.*)$")
	if tone == "good" or tone == "bad" or tone == "same" then
		return tone, rest :: string
	end
	local first = string.sub(line, 1, 1)
	return (if first == "+" then "good" elseif first == "-" then "bad" else "same"), line
end

-- WHERE A MARKER GOES in its parent: (wx, wy) is the waypoint in VIEWPORT pixels (the camera's own: what waypoint
-- returns); (ax, ay) the parent's AbsolutePosition, (ix, iy) GuiService:GetGuiInset(). AbsolutePosition counts from
-- UNDER the top bar's inset on every screen (a screen that ignores the inset sits at y = -inset), so the parent's
-- corner in viewport pixels is AbsolutePosition + inset (measured in Studio 2026-11-20: taken as AbsolutePosition
-- alone, a marker on a screen that keeps the inset sat 57 px under its target). -> the marker's offset Position
function UiCombat.placeIn(wx: number, wy: number, ax: number, ay: number, ix: number, iy: number): (number, number)
	return wx - (ax + ix), wy - (ay + iy)
end

return UiCombat
