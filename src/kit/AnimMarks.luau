--!strict
-- AnimMarks — ONE EFFECT FOR ONE MARKER (the owner's older list, AN-34: "cosmetic marker timing needs reconciliation
-- with gameplay events ... presentation timestamps, deduplication and cancellation rules without moving damage
-- authority to the client"). Pure: no services, no Instances. The Instance side is Anim.marker (src/kit/Anim).
--
-- WHAT THE ENGINE DOES WITH A MARKER (measured in Studio, 2026-11-15, the kit's kesa, its Hit at 0.433 s):
--   it fires each time the clip's time CROSSES it: once a play, once a loop pass, again after the time is wound
--     back behind it, again on a second Play of the same track (and once played backwards);
--   it does NOT fire while the clip is frozen on it (a hit-stop: speed 0), when the time JUMPS over it (a clip
--     entered late skips every marker before its entry), or after the track is stopped (at once or fading out);
--   it fires LATE: the handler runs on the first frame past the marker (4 to 63 ms late at 25 frames a second).
-- So an effect hung on a marker can come twice for one action (a rewind inside one play) and not at all (an entry
-- past it). Damage is not hung on markers: the server's Moves decides hits from frame data (src/kit/Moves).
--
-- THE RULE. One STATE a track (its pass, whether it was cancelled, where it was entered); one LISTENER a
-- connection (what THAT handler has taken: two handlers on one marker each get it).
--   WHICH marker fired: of the clip's events of that name, in time order, the EARLIEST one this listener has not
--     taken in this pass that the clip's time has reached (its time <= now, a frame's grace). None left: the fire
--     is a duplicate - dropped. So two Hits a tenth of a second apart are taken first, then second, however late
--     the handlers run or even when one long frame crosses both; and a marker crossed again after a rewind finds
--     everything behind it taken.
--   A new PASS lets every marker be taken once more: the track was played again (the caller says so), or - a
--     LOOPED track - its time went back (it wrapped; which of the engine's loop signal and the marker comes first
--     in the wrap frame does not matter). A marker at a looped clip's very end whose handler runs after the wrap
--     is still taken, for the pass it belongs to.
--   After a CANCEL (the move was cancelled, the track stopped) nothing is taken until a new pass.
--   A clip ENTERED late owes nothing before its entry: events before it are never the one that fired.
--   What is taken comes with its record: the marker's OWN time in the clip, how late the handler is (in the
--     clip's seconds), which pass, and the count of that marker for this listener.
--   AnimMarks.skipped(events, from, to): the markers an entry at `to` jumped over - for the caller to apply the
--     ones that set a STATE (a face, a vanish) and drop the one-shots (a whoosh).

local AnimMarks = {}

AnimMarks.EPS = 0.02 -- seconds a marker may lie AHEAD of the time read and still be the one that fired
AnimMarks.WRAP = 0.1 -- seconds from a looped clip's end a marker may be, for its handler to run after the wrap

export type Event = { name: string, t: number, value: any? }
export type Listener = { pass: number, taken: { [string]: boolean }, count: { [string]: number }, last: number }
export type State = { pass: number, cancelled: boolean, from: number, own: Listener }
export type Record = { name: string, index: number, time: number, late: number, pass: number, count: number }

function AnimMarks.listener(): Listener
	return { pass = 0, taken = {}, count = {}, last = -math.huge }
end

function AnimMarks.new(): State
	return { pass = 1, cancelled = false, from = -math.huge, own = AnimMarks.listener() }
end

-- a new pass: the track was played again (a looped track's wrap needs no telling: take sees it)
function AnimMarks.pass(state: State)
	state.pass += 1
	state.cancelled = false
	state.from = -math.huge
end

-- the move was cancelled, the track stopped: nothing more is taken until a new pass
function AnimMarks.cancel(state: State)
	state.cancelled = true
end

-- the clip was ENTERED at `at` seconds (pose / distance matching): markers before it are not owed
function AnimMarks.entered(state: State, at: number)
	if at == at then
		state.from = at
	end
end

-- the times of the clip's events of one name, ascending
local function timesOf(events: { Event }?, name: string): { number }
	local out: { number } = {}
	local list: { Event } = events or {}
	for _, e in list do
		if type(e) == "table" and e.name == name and type(e.t) == "number" and e.t == e.t then
			table.insert(out, e.t)
		end
	end
	table.sort(out)
	return out
end

-- A MARKER FIRED: is it taken? name: the marker; at: the track's time when the handler runs; events: the clip's
-- own (for which of several it is, and its own time); mine: this connection's listener (left out: the state's
-- own - one handler a track); looped / length: the track's (for a wrap). Returns its record, or nil when it is
-- dropped (a duplicate, a cancelled track, a time that is not a number).
function AnimMarks.take(
	state: State,
	name: string,
	at: number,
	events: { Event }?,
	mine: Listener?,
	looped: boolean?,
	length: number?
): Record?
	if state.cancelled or at ~= at then
		return nil
	end
	local me = mine or state.own
	if me.pass ~= state.pass then
		me.pass = state.pass
		table.clear(me.taken)
		me.last = -math.huge
	end
	if looped and at + AnimMarks.EPS < me.last then
		table.clear(me.taken) -- (a looped clip's time went back: it wrapped)
	end
	me.last = at
	local times = timesOf(events, name)
	local index: number?, time = nil, at
	if #times == 0 then
		index = 1 -- (a marker the clip's events do not list: one slot)
		if me.taken[name .. "#1"] then
			return nil
		end
	else
		for i, t in times do
			if not me.taken[name .. "#" .. i] and t <= at + AnimMarks.EPS and t >= state.from - AnimMarks.EPS then
				index, time = i, t
				break
			end
		end
		if not index then
			-- a looped clip's last marker, its handler run just after the wrap: taken for the pass that ended
			-- (not marked: this pass's own crossing of it is still to come)
			local last = times[#times]
			if looped and length and length == length and at < AnimMarks.WRAP and last >= length - AnimMarks.WRAP then
				local count = (me.count[name] or 0) + 1
				me.count[name] = count
				return {
					name = name,
					index = #times,
					time = last,
					late = at + length - last,
					pass = state.pass,
					count = count,
				}
			end
			return nil
		end
	end
	me.taken[name .. "#" .. (index :: number)] = true
	local count = (me.count[name] or 0) + 1
	me.count[name] = count
	return {
		name = name,
		index = index :: number,
		time = time,
		late = math.max(at - time, 0),
		pass = state.pass,
		count = count,
	}
end

-- THE MARKERS AN ENTRY JUMPED OVER: every event with from <= t < to, in the clip's order (a clip entered at `to`
-- by its pose or its distance never fires them; one exactly AT the entry does fire)
function AnimMarks.skipped(events: { Event }?, from: number, to: number): { Event }
	local out: { Event } = {}
	local list: { Event } = events or {}
	for _, e in list do
		if type(e) == "table" and type(e.t) == "number" and e.t >= from and e.t < to then
			table.insert(out, e)
		end
	end
	table.sort(out, function(a, b)
		return a.t < b.t
	end)
	return out
end

-- the last skipped event of a name (the STATE a late entry must still have: the face the clip had put on)
function AnimMarks.lastSkipped(events: { Event }?, name: string, to: number): Event?
	local found: Event? = nil
	for _, e in AnimMarks.skipped(events, -math.huge, to) do
		if e.name == name then
			found = e
		end
	end
	return found
end

return AnimMarks
