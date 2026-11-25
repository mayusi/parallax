--!strict
-- VfxSequenceRules (kit) — the RULES of a choreographed multi-shot sequence (LIMITATIONS_FIXES_V4 §3.4 step 3, §13.3.3:
-- "V5 Choreographed Multi-Shot Engine"), pure: no services, no instances. src/kit/VfxSequence.luau plays what these
-- compile; kit/vfx/sequence.py checks and draws the same file through them (kit/vfx/sequence.luau).
--
-- A sequence (assets/effects/sequences/<name>.seq.json) is beats on the 60 fps SEQUENCE clock:
--   { "schema": 1, "name": "...", "fps": 60, "kind": "hero" | "plain",
--     "beats": [ { "t_frame": 0, "name": "charge",
--                  "camera_cut"?: { "shot": "wide" | "close" | "low" | "high" | "over" | "side" | "back" | "top" },
--                  "fov_punch"?: { "delta": -40..40 degrees, "frames": 1..120 },
--                  "shake"?: { "amp": 0..10 degrees, "frames": 1..240 },
--                  "mood_push"?: { "values": { <VfxMood key>: value }, "frames": 1..240, "priority"?: n },
--                  "impact_plate"?: { "plate": "<plate key>", "frames": 1..30, "rate"?: 1 | 2 | 3 },
--                  "hitstop"?: { "frames": 1..30 },
--                  "vfx_layers"?: { "<preset>" ... },  "sfx_event"?: "<event>",
--                  "victim_reaction"?: { "power": 0..10, "normal"?: [x, y, z] } } ... ] }
-- A "hero" sequence must have the V5 shape: Charge -> ONE impact beat (a 1-frame mood push + an impact plate + a
-- hitstop, on the same frame) -> a multi-cut reveal (two or more camera cuts after it, each held long enough to read).
--
-- The clock: a step of dt crosses the frames (from, to]; an event fires in the first step whose time reaches its
-- frame - never early, late by less than one step (at 30 fps or faster: within one 60 fps frame). An END never fires
-- in the step its start fired in: a 1-frame mood at 30 fps would otherwise be pushed and popped before any frame was
-- drawn - the 1-frame beat the owner asked for (flame_arc: "a 1f pink beat") would never be seen.
local Rules = {}

Rules.FPS = 60
Rules.SHOTS = { "wide", "close", "low", "high", "over", "side", "back", "top" }
Rules.MIN_CUT = 6 -- frames a reveal cut is held at least (a cut shorter than 0.1 s does not read)
Rules.MIN_CHARGE = 12 -- frames the charge runs before the impact at least
Rules.MAX_FRAMES = 60 * 30 -- a sequence is 30 s at most
-- the order events of ONE frame fire in: the world is frozen and the mood laid before the plate and the cut show
Rules.ORDER = {
	"hitstop",
	"mood_push",
	"camera_cut",
	"fov_punch",
	"shake",
	"impact_plate",
	"vfx_layers",
	"sfx_event",
	"victim_reaction",
}
local BEAT_KEYS = {
	t_frame = true,
	name = true,
	camera_cut = true,
	fov_punch = true,
	shake = true,
	mood_push = true,
	impact_plate = true,
	hitstop = true,
	vfx_layers = true,
	sfx_event = true,
	victim_reaction = true,
}
local TOP_KEYS = { schema = true, name = true, fps = true, kind = true, beats = true, about = true }

export type Event = {
	frame: number,
	kind: string, -- one of Rules.ORDER, or "<kind>_end"
	beat: number, -- the beat's index (1-based)
	data: any,
	ends: number?, -- the frame its end falls on (a start with a duration)
}
export type Timeline = { name: string, frames: number, events: { Event } }
export type Clock = { t: number, frame: number, fired: { [Event]: number }, step: number }

local function isInt(v: any, lo: number, hi: number): boolean
	return type(v) == "number" and v == v and v == math.floor(v) and v >= lo and v <= hi
end

local function isNum(v: any, lo: number, hi: number): boolean
	return type(v) == "number" and v == v and v >= lo and v <= hi
end

-- validate(seq) -> (ok, problems): every problem a sentence that names the beat and the field
function Rules.validate(seq: any): (boolean, { string })
	local bad: { string } = {}
	local function say(s: string)
		table.insert(bad, s)
	end
	if type(seq) ~= "table" then
		return false, { "a sequence is a table (the .seq.json's top object)" }
	end
	for k in seq do
		if not TOP_KEYS[k] then
			say(`unknown key "{tostring(k)}" at the top (a typo is never ignored)`)
		end
	end
	if seq.schema ~= 1 then
		say("schema is 1")
	end
	if type(seq.name) ~= "string" or not string.match(seq.name, "^[%w_]+$") then
		say("name is letters, digits and _")
	end
	if seq.fps ~= Rules.FPS then
		say(`fps is {Rules.FPS} (the game clock the beats are counted on)`)
	end
	if seq.kind ~= nil and seq.kind ~= "hero" and seq.kind ~= "plain" then
		say(`kind is "hero" or "plain"`)
	end
	local beats = seq.beats
	if type(beats) ~= "table" or #beats == 0 then
		say("beats is a list of one or more beats")
		return false, bad
	end
	local last = -1
	for i, b in beats do
		local at = `beat {i}`
		if type(b) ~= "table" then
			say(`{at} is a table`)
			continue
		end
		at = if type(b.name) == "string" then `beat {i} ({b.name})` else at
		for k in b do
			if not BEAT_KEYS[k] then
				say(`{at}: unknown key "{tostring(k)}"`)
			end
		end
		if not isInt(b.t_frame, 0, Rules.MAX_FRAMES) then
			say(`{at}: t_frame is a whole frame 0..{Rules.MAX_FRAMES}`)
		elseif b.t_frame <= last then
			say(`{at}: t_frame {b.t_frame} is not after the beat before ({last}) - beats run forward`)
		else
			last = b.t_frame
		end
		local c = b.camera_cut
		if c ~= nil and (type(c) ~= "table" or not table.find(Rules.SHOTS, c.shot)) then
			say(`{at}: camera_cut.shot is one of {table.concat(Rules.SHOTS, ", ")}`)
		end
		local f = b.fov_punch
		if f ~= nil and (type(f) ~= "table" or not isNum(f.delta, -40, 40) or not isInt(f.frames, 1, 120)) then
			say(`{at}: fov_punch is \{ delta -40..40, frames 1..120 }`)
		end
		local s = b.shake
		if s ~= nil and (type(s) ~= "table" or not isNum(s.amp, 0, 10) or not isInt(s.frames, 1, 240)) then
			say(`{at}: shake is \{ amp 0..10, frames 1..240 }`)
		end
		local m = b.mood_push
		if m ~= nil then
			local okv = type(m) == "table" and type(m.values) == "table" and next(m.values) ~= nil
			if okv then
				for k, v in m.values do
					local kindOk = type(v) == "number" or type(v) == "string" or type(v) == "table"
					if type(k) ~= "string" or not kindOk or (type(v) == "number" and v ~= v) then
						okv = false
					end
				end
			end
			if not okv or not isInt(m.frames, 1, 240) or (m.priority ~= nil and not isNum(m.priority, -100, 100)) then
				say(`{at}: mood_push is \{ values \{ key = value }, frames 1..240, priority? }`)
			end
		end
		local p = b.impact_plate
		if
			p ~= nil
			and (
				type(p) ~= "table"
				or type(p.plate) ~= "string"
				or not isInt(p.frames, 1, 30)
				or (p.rate ~= nil and not isInt(p.rate, 1, 3))
			)
		then
			say(`{at}: impact_plate is \{ plate "<key>", frames 1..30, rate? 1..3 }`)
		end
		local h = b.hitstop
		if h ~= nil and (type(h) ~= "table" or not isInt(h.frames, 1, 30)) then
			say(`{at}: hitstop is \{ frames 1..30 }`)
		end
		local v = b.vfx_layers
		if v ~= nil then
			local okl = type(v) == "table" and #v >= 1 and #v <= 16
			if okl then
				for _, n in v do
					okl = okl and type(n) == "string" and n ~= ""
				end
			end
			if not okl then
				say(`{at}: vfx_layers is a list of 1..16 preset names`)
			end
		end
		if b.sfx_event ~= nil and (type(b.sfx_event) ~= "string" or b.sfx_event == "") then
			say(`{at}: sfx_event is an event name`)
		end
		local r = b.victim_reaction
		if r ~= nil then
			local okr = type(r) == "table" and isNum(r.power, 0, 10)
			if okr and r.normal ~= nil then
				okr = type(r.normal) == "table"
					and #r.normal == 3
					and isNum(r.normal[1], -1e3, 1e3)
					and isNum(r.normal[2], -1e3, 1e3)
					and isNum(r.normal[3], -1e3, 1e3)
			end
			if not okr then
				say(`{at}: victim_reaction is \{ power 0..10, normal? [x, y, z] }`)
			end
		end
	end
	if #bad == 0 and seq.kind == "hero" then
		for _, s in Rules.shape(seq) do
			say(s)
		end
	end
	return #bad == 0, bad
end

-- the impact beat of a sequence: the beat with a 1-frame mood push, a plate and a hitstop (nil: none)
function Rules.impactBeat(seq: any): number?
	for i, b in seq.beats do
		if b.mood_push and b.mood_push.frames == 1 and b.impact_plate and b.hitstop then
			return i
		end
	end
	return nil
end

-- shape(seq) -> what a HERO sequence is missing of the V5 shape (empty: it has it)
function Rules.shape(seq: any): { string }
	local miss: { string } = {}
	local beats = seq.beats
	local impacts = {}
	for i, b in beats do
		if b.mood_push and b.mood_push.frames == 1 and b.impact_plate and b.hitstop then
			table.insert(impacts, i)
		end
	end
	if #impacts == 0 then
		table.insert(
			miss,
			"a hero sequence has an IMPACT beat: a 1-frame mood_push, an impact_plate and a hitstop on one frame"
		)
		return miss
	elseif #impacts > 1 then
		table.insert(
			miss,
			`a hero sequence has ONE impact beat ({#impacts} found: beats {table.concat(impacts, ", ")})`
		)
	end
	local hit = beats[impacts[1]]
	if hit.t_frame - beats[1].t_frame < Rules.MIN_CHARGE then
		table.insert(
			miss,
			`the charge runs {hit.t_frame - beats[1].t_frame} frames before the impact (at least {Rules.MIN_CHARGE}: the eye needs the wind-up)`
		)
	end
	local cuts = {}
	for i = impacts[1] + 1, #beats do
		if beats[i].camera_cut then
			table.insert(cuts, i)
		end
	end
	if #cuts < 2 then
		table.insert(miss, `the reveal after the impact is {#cuts} camera cut(s): a multi-cut reveal is two or more`)
	end
	for k, i in cuts do
		local nextAt = if cuts[k + 1] then beats[cuts[k + 1]].t_frame else Rules.frames(seq)
		if nextAt - beats[i].t_frame < Rules.MIN_CUT then
			table.insert(
				miss,
				`the cut at beat {i} is held {nextAt - beats[i].t_frame} frames (at least {Rules.MIN_CUT} to read)`
			)
		end
	end
	return miss
end

-- the sequence's length in frames: its last beat, or the last thing a beat starts, whichever ends later
function Rules.frames(seq: any): number
	local n = 0
	for _, b in seq.beats do
		n = math.max(n, b.t_frame + 1)
		for _, key in { "fov_punch", "shake", "mood_push", "impact_plate", "hitstop" } do
			local v = b[key]
			if type(v) == "table" and type(v.frames) == "number" then
				n = math.max(n, b.t_frame + v.frames)
			end
		end
	end
	-- the last cut is held as long as the reveal's minimum at least
	local last = seq.beats[#seq.beats]
	if last and last.camera_cut then
		n = math.max(n, last.t_frame + Rules.MIN_CUT)
	end
	return n
end

local RANK: { [string]: number } = {}
for i, k in Rules.ORDER do
	RANK[k] = i
	RANK[k .. "_end"] = 100 + i
end

-- compile(seq) -> the timeline: every start and end as an event on its frame, in the order of Rules.ORDER within a
-- frame (ends of a frame before its starts). Raises on a sequence that does not validate.
function Rules.compile(seq: any): Timeline
	local ok, bad = Rules.validate(seq)
	if not ok then
		error("VfxSequenceRules.compile: " .. table.concat(bad, "; "), 2)
	end
	local events: { Event } = {}
	for i, b in seq.beats do
		for _, kind in Rules.ORDER do
			local v = b[kind]
			if v ~= nil then
				local dur = if type(v) == "table" and type(v.frames) == "number" then v.frames else nil
				local ev: Event = { frame = b.t_frame, kind = kind, beat = i, data = v, ends = nil }
				if dur then
					ev.ends = b.t_frame + dur
					table.insert(events, { frame = b.t_frame + dur, kind = kind .. "_end", beat = i, data = v })
				end
				table.insert(events, ev)
			end
		end
	end
	table.sort(events, function(a, b)
		if a.frame ~= b.frame then
			return a.frame < b.frame
		end
		local ea, eb = string.sub(a.kind, -4) == "_end", string.sub(b.kind, -4) == "_end"
		if ea ~= eb then
			return ea -- the old beat lets go before the new one takes hold
		end
		if RANK[a.kind] ~= RANK[b.kind] then
			return RANK[a.kind] < RANK[b.kind]
		end
		return a.beat < b.beat
	end)
	return { name = seq.name, frames = Rules.frames(seq), events = events }
end

function Rules.clock(): Clock
	return { t = 0, frame = -1, fired = {}, step = 0 }
end

-- step(timeline, clock, dt) -> the events that fire in this step, in order. dt in seconds (a frame's delta); a
-- negative or NaN dt is a zero step. An end whose start fired in THIS step waits for the next one.
function Rules.step(tl: Timeline, clock: Clock, dt: number): { Event }
	if type(dt) ~= "number" or dt ~= dt or dt < 0 or dt == math.huge then
		dt = 0
	end
	clock.step += 1
	clock.t += dt
	local reach = math.floor(clock.t * Rules.FPS + 1e-6)
	local out: { Event } = {}
	local startedNow: { [string]: boolean } = {}
	for _, ev in tl.events do
		if ev.frame > reach then
			break
		end
		if clock.fired[ev] == nil then
			local isEnd = string.sub(ev.kind, -4) == "_end"
			local key = `{ev.beat}:{if isEnd then string.sub(ev.kind, 1, -5) else ev.kind}`
			if isEnd and startedNow[key] then
				continue -- held over: its start has not been drawn yet
			end
			clock.fired[ev] = clock.step
			table.insert(out, ev)
			if not isEnd then
				startedNow[key] = true
			end
		end
	end
	clock.frame = reach
	return out
end

-- done(timeline, clock) -> has every event fired
function Rules.done(tl: Timeline, clock: Clock): boolean
	for _, ev in tl.events do
		if clock.fired[ev] == nil then
			return false
		end
	end
	return true
end

return Rules
