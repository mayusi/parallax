--!strict
-- AnimPaired — WHEN A PAIRED MOVE BREAKS, AND WHAT EACH BODY DOES THEN (the owner's older list, AN-32: "extend
-- contact / timeline contracts to interruptible paired gameplay, with arbitration for stun, death, separation and
-- ownership changes ... paired moves stay aligned or exit safely under interrupts, late observers and server
-- hitches").
--
-- A paired move is two (or more) bodies on ONE timeline: a grab, a throw, a finisher, a clash (src/kit/Cutscene
-- plays one: every body's root on the planned path, every track at the planned time). It stayed aligned because
-- nothing was allowed to happen to it. This module is the rule for what DOES happen in a game:
--   a body is GONE (its player left, it was destroyed)        the move ends for everyone, at once
--   a body DIES                                                the move ends (a finisher that kills ends itself)
--   a body is STUNNED by somebody outside the move             it breaks - until the move COMMITS
--   a body is APART from where the plan has it                 it breaks - until the move COMMITS (it was moved
--                                                               by something stronger than the move: a teleport)
--   a body's OWNER changes (its network owner)                 the machine that lost it stops driving it; the
--                                                               move goes on where it is still owned
-- COMMIT: a paired move may say a time after which only GONE and DEAD end it (a throw past the lift, a finisher
-- past the stab: stopping there leaves a body in the air). Unsaid: it never commits.
-- ONE verdict, the same on every machine that asks with the same facts: reasons are ranked, the earliest body in
-- the cast's order wins a tie. What each body DOES on a break is `AnimPaired.exits`: the one the break is about
-- and the others are told apart (the stunned one staggers, the other lets go).
-- THE CLOCK: everybody plays the time the SERVER's clock says (seconds since it started the move): a late
-- observer joins at that time, a machine that fell behind (a hitch) or ran ahead is put back on it when it is
-- more than RESYNC off - snapped, not played fast (two bodies at two speeds are not aligned).
-- NOT HERE: what a game does with a break (damage, a recovery clip of its own: it is told the reason and who);
-- rollback or prediction of a paired move on a client (the server plays the bodies).

local AnimPaired = {}

export type Facts = {
	present: boolean, -- the body is in the world (its model and root have a parent)
	alive: boolean,
	stunned: boolean?, -- by somebody outside the move
	apart: number?, -- studs between where the body is and where the plan last put it
	owned: boolean?, -- this machine still owns the body (unsaid: it does)
}
export type Rule = {
	commit: number?, -- seconds into the move after which only "gone" and "death" end it
	maxApart: number?, -- studs (default MAX_APART)
	stun: boolean?, -- false: a stun from outside does not break it (a super-armoured grab)
	fatal: { [string]: boolean }?, -- roles whose death is the move's own (a finisher's victim): not a break
}
export type Verdict = { reason: string, who: string, at: number }

AnimPaired.MAX_APART = 3 -- studs a body may be from its planned place (a hit-stop shake, a rounding: far less)
AnimPaired.RESYNC = 0.1 -- seconds a machine's time may differ from the server's before it is put back on it
AnimPaired.RANK = { gone = 1, death = 2, stun = 3, apart = 4 } -- (1 wins)

-- the move at `t` seconds, each role's facts, in the cast's ORDER (a list of role names: the same on every
-- machine) -> nil while it runs, else why it ends and for whom
function AnimPaired.verdict(rule: Rule?, t: number, order: { string }, facts: { [string]: Facts }): Verdict?
	local r: Rule = rule or {}
	local commit = r.commit
	local committed = commit ~= nil and t >= commit
	local best: Verdict? = nil
	local function offer(reason: string, who: string)
		local b = best
		if not b or AnimPaired.RANK[reason] < AnimPaired.RANK[b.reason] then
			best = { reason = reason, who = who, at = t }
		end
	end
	for _, role in order do
		local f = facts[role]
		if not f or not f.present then
			offer("gone", role)
		elseif not f.alive then
			if not (r.fatal and r.fatal[role]) then
				offer("death", role)
			end
		elseif not committed then
			if f.stunned and r.stun ~= false then
				offer("stun", role)
			end
			local apart = f.apart
			-- (a rule's distance that is no distance: the default, not "always" or "never")
			local said = r.maxApart
			local most: number = if said and said == said and said > 0 then said else AnimPaired.MAX_APART
			if apart and apart == apart and apart > most then
				offer("apart", role)
			end
		end
	end
	return best
end

-- may this machine go on driving a body? (a client that lost a body's ownership stops writing it; the server -
-- or whoever owns it now - goes on)
function AnimPaired.drives(f: Facts?): boolean
	return f ~= nil and f.present and f.owned ~= false
end

-- WHAT EACH BODY DOES when the move ends early. `self`: the body the verdict is about. -> a word the game (or
-- src/kit/Cutscene) acts on:
--   "none"     nothing can be done for it (it is gone)
--   "fall"     it is dead: let go of it, its own death plays (a ragdoll, a death clip)
--   "stagger"  it was stunned from outside: its tracks stop, a hit reaction is the game's to play
--   "release"  it is unharmed: its tracks fade, it stands where it is, free
-- (a body let go in the air falls when it was not anchored before the move: the scene player gives every body
-- back as it was)
function AnimPaired.exits(v: Verdict, role: string): string
	if role == v.who then
		if v.reason == "gone" then
			return "none"
		elseif v.reason == "death" then
			return "fall"
		elseif v.reason == "stun" then
			return "stagger"
		end
	end
	return "release"
end

-- the time to play: `mine` is this machine's own count, `server` the seconds since the server started the move
-- (nil: there is no shared clock - a local scene) -> the time, and whether it was snapped
function AnimPaired.resync(mine: number, server: number?, tolerance: number?): (number, boolean)
	if not server or server ~= server then
		return mine, false
	end
	if mine ~= mine then
		return server, true
	end
	if math.abs(mine - server) > (tolerance or AnimPaired.RESYNC) then
		return server, true
	end
	return mine, false
end

-- a LATE OBSERVER: the move began `since` seconds ago and is `length` long -> where to join it (nil: it is over -
-- show nothing)
function AnimPaired.joinAt(since: number, length: number): number?
	if since ~= since or length ~= length or length <= 0 or since >= length then
		return nil
	end
	return math.max(0, since)
end

return AnimPaired
