--!strict
-- MovesRules (ReplicatedStorage.kit.MovesRules) — the PURE half of moves-as-data (no game APIs; specs in
-- kit/test/spec/moves.spec.luau). A MOVE is a JSON file (assets/moves/<Name>.json):
-- { "name": "BgM1_1", "anim": "BgM11",
--   "frames": { "fps": 60, "startup": 15, "active": 3, "recovery": 30 }   (or "frames": "from_anim": the anim
--             lane's measured phases — anticipation / action / recovery — in build/animations/<anim>.metrics.json)
--   "hitboxes": [ { "frames": [15, 17], "size": [5, 5, 6], "offset": [0, 0, -3.5] } ],   (frames inside active)
--   "damage": 6, "stun": 0.45, "knockback": [0, 4, 18], "hitstop": 0.06, "blockstun": 0.3,
--   "block": "blockable" | "chip" | "unblockable", "parryable": true,
--   "cancel": { "into": ["BgM1_2", "Dash"], "from": 18, "to": 40 },  (frames)
--   "cooldown": 0, "vfx": [ { "frame": 15, "preset": "slash" } ], "sfx": [ { "frame": 2, "event": "SwordSwing", "weight": 0.3 } ],
--   "onHit": { "sfx": "SwordHit", "vfx": "hit_sparks", "shake": 0.2 } }
local MovesRules = {}

export type Timeline = { fps: number, startup: number, active: number, recovery: number, total: number }
export type Defender = {
	blocking: boolean?,
	parryAt: number?, -- the time the defender pressed parry (seconds, same clock as `now`)
	now: number,
	iframes: boolean?,
}
export type Outcome = {
	kind: string, -- "hit" | "blocked" | "chip" | "parried" | "dodged"
	damage: number,
	stun: number,
	hitstop: number,
	knockback: { number },
	attackerStun: number, -- a parry stuns the attacker
}

local PARRY_WINDOW = 0.15 -- seconds: fighting-game windows are 6-10 frames at 60 fps
-- a parry is a short window, then a lockout: pressing parry faster than this cannot hold the window open forever
-- (a client spamming parry 7 times a second beat every attack)
MovesRules.PARRY_WINDOW = PARRY_WINDOW
MovesRules.PARRY_COOLDOWN = 0.75
-- WHICH CLIP a move plays (animation masking): its upper-body version (the build makes one for a move that says
-- "upper": Meta.<anim>.upper = "<anim>Upper", the same clip with its legs left out) while the character is MOVING,
-- so the walk keeps the legs under the attack; the move itself when it stands. meta: the build's clip metadata.
function MovesRules.clipFor(anim: string, meta: any, moving: boolean): string
	local m = if type(meta) == "table" then meta[anim] else nil
	local upper = if type(m) == "table" then m.upper else nil
	if moving and type(upper) == "string" and upper ~= "" and type(meta[upper]) == "table" then
		return upper
	end
	return anim
end

-- how fast the character must be asked to move for a move to count as made on the move (Humanoid.MoveDirection's
-- length: 0 standing, 1 walking; a stick barely off centre is not walking)
MovesRules.MOVING = 0.1

-- may a parry be pressed now? lastParryAt: when the last one was (nil: never). The window itself is PARRY_WINDOW
-- (resolve reads it); this is the lockout between two presses
function MovesRules.parryAllowed(lastParryAt: number?, now: number): boolean
	if type(lastParryAt) ~= "number" or lastParryAt ~= lastParryAt or now ~= now then
		return true
	end
	return now - lastParryAt >= MovesRules.PARRY_COOLDOWN
end

-- the parry a defender HAS when a hit lands (what resolve reads as defender.parryAt; nil = none). A parry is its window
-- only, and only while the defender is not attacking: a move started at or after the parry closes it. (A parry and an
-- attack sent in ONE frame used to give the attack a parry's protection for the window's 0.15 s - every hit on the
-- attacker resolved "parried", the opponent stunned, the attack running on: the Studio red-team playtest
-- dojo_combat_redteam, 2026-11-20.) The parry keeps its time for the lockout (parryAllowed) either way.
function MovesRules.parryAtContact(parryAt: number?, moveStarted: number?): number?
	if type(parryAt) ~= "number" or parryAt ~= parryAt then
		return nil
	end
	if type(moveStarted) == "number" and moveStarted >= parryAt then
		return nil
	end
	return parryAt
end

local COMBO_SCALING = 0.1 -- each further hit in a combo does 10 % less, down to 40 %

local function num(v: any, fallback: number): number
	if type(v) == "number" and v == v and v ~= math.huge and v ~= -math.huge then
		return v
	end
	return fallback
end

function MovesRules.timeline(move: any): Timeline
	local f = type(move) == "table" and move.frames
	if type(f) ~= "table" then
		f = {}
	end
	local startup = math.max(0, math.floor(num(f.startup, 0)))
	local active = math.max(1, math.floor(num(f.active, 1)))
	local recovery = math.max(0, math.floor(num(f.recovery, 0)))
	return {
		fps = math.max(1, num(f.fps, 60)),
		startup = startup,
		active = active,
		recovery = recovery,
		total = startup + active + recovery,
	}
end

-- the phase at `t` seconds into the move, and the frame number (0-based)
function MovesRules.phaseAt(move: any, t: number): (string, number)
	local tl = MovesRules.timeline(move)
	local frame = math.floor(math.max(0, num(t, 0)) * tl.fps + 1e-6)
	if frame < tl.startup then
		return "startup", frame
	elseif frame < tl.startup + tl.active then
		return "active", frame
	elseif frame < tl.total then
		return "recovery", frame
	end
	return "done", frame
end

-- the hitboxes live on this frame
function MovesRules.hitboxesAt(move: any, frame: number): { any }
	local out = {}
	for _, hb in (type(move) == "table" and move.hitboxes) or {} do
		local fr = hb.frames
		if type(fr) == "table" and frame >= num(fr[1], -1) and frame <= num(fr[2], -1) then
			table.insert(out, hb)
		end
	end
	return out
end

-- the hitboxes live on ANY frame after `fromFrame` up to and including `toFrame`, each once (in the move's order). The
-- server's hit loop checks every frame passed since its last step: a step that comes late (a server hitch - in a
-- background Studio window the server stepped at 0.17 s and then 0.32 s, over a 0.233..0.283 s hit window) would
-- otherwise skip the whole window and the hit is lost (the moves_hitstop playtest, 2026-11-17).
function MovesRules.hitboxesBetween(move: any, fromFrame: number, toFrame: number): { any }
	local out = {}
	-- (a hitbox counts only inside the move's ACTIVE frames, as phaseAt says - the rule the per-frame check had)
	local tl = MovesRules.timeline(move)
	local first, last = tl.startup, tl.startup + tl.active - 1
	for _, hb in (type(move) == "table" and move.hitboxes) or {} do
		local fr = hb.frames
		if type(fr) == "table" then
			local a, b = math.max(num(fr[1], -1), first), math.min(num(fr[2], -1), last)
			if a <= b and b > fromFrame and a <= toFrame then
				table.insert(out, hb)
			end
		end
	end
	return out
end

function MovesRules.canCancel(move: any, t: number, into: string): boolean
	local c = type(move) == "table" and move.cancel
	if type(c) ~= "table" or type(c.into) ~= "table" or not table.find(c.into, into) then
		return false
	end
	local _, frame = MovesRules.phaseAt(move, t)
	return frame >= num(c.from, math.huge) and frame <= num(c.to, -math.huge)
end

-- INPUT BUFFER (AAA gaps v2 C1): seconds from `t` (into `move`) until `into` may start out of it - its cancel window
-- opening, or the move ending. A press up to the buffer (~0.15-0.2 s in fighting games) before that moment is held and
-- fired then, so a player who presses a hair early is not eaten. 0 = now; math.huge = never inside this move
function MovesRules.waitFor(move: any, t: number, into: string): number
	local tl = MovesRules.timeline(move)
	local _, frame = MovesRules.phaseAt(move, t)
	local c = type(move) == "table" and move.cancel
	local opens = tl.total
	if type(c) == "table" and type(c.into) == "table" and table.find(c.into, into) then
		local from, to = num(c.from, math.huge), num(c.to, -math.huge)
		if frame <= to then
			opens = math.min(opens, math.max(from, frame))
		end
	end
	return math.max(0, opens / tl.fps - math.max(0, num(t, 0)))
end

-- may `name` start now? The SERVER decides the combo step: a combo move (in set.combo) after the first one is only
-- allowed straight out of the previous step (its cancel window) or within `gap` seconds after it ended — a client
-- cannot open with the finisher or spam the fastest step. Cooldowns per move. Returns ok, reason, the next combo index.
-- state = { moveName?, moveT? (seconds into the current move), lastName?, lastEnded?, comboIndex, lastUsed = { [name]: t } }
-- lastEnded is the previous move's end (prevEndedAt): kept across the move's exit, on the same clock as `now` (the
-- caller's game clock - Workspace:GetServerTimeNow, ~1.79e9; this module never reads a clock). Out of an ENDED move,
-- nothing starts before MIN_GAP has run ("gap"): no move starts on the frame the last one ended.
-- (MIN_GAP_EPS: a difference of two ~1.79e9 numbers is off by up to ~2.4e-7 s; one frame later must still pass)
MovesRules.MIN_GAP = 1 / 60
local MIN_GAP_EPS = 1e-6
function MovesRules.allowed(set: any, state: any, name: string, now: number, gap: number?): (boolean, string?, number)
	local move = set.moves and set.moves[name]
	if type(move) ~= "table" then
		return false, "unknown move", 0
	end
	local cd = num(move.cooldown, 0)
	local last = state.lastUsed and state.lastUsed[name]
	if cd > 0 and last and now - last < cd then
		return false, "cooldown", 0
	end
	local current = state.moveName and set.moves[state.moveName]
	if current then
		local phase = MovesRules.phaseAt(current, state.moveT or 0)
		if phase ~= "done" and not MovesRules.canCancel(current, state.moveT or 0, name) then
			return false, "busy", 0
		end
	end
	local ended = state.lastEnded
	if not current and type(ended) == "number" and now - ended < MovesRules.MIN_GAP - MIN_GAP_EPS then
		return false, "gap", 0
	end
	local chain = set.combo or {}
	local idx = table.find(chain, name)
	if not idx or idx == 1 then
		return true, nil, 1
	end
	local prev = chain[idx - 1]
	local fromCancel = state.moveName == prev and current ~= nil
	local fromGap = state.lastName == prev and state.lastEnded ~= nil and now - state.lastEnded <= (gap or 0.9)
	if fromCancel or fromGap then
		return true, nil, (state.comboIndex or 0) + 1
	end
	return false, `out of combo order ({name} follows {prev})`, 0
end

-- what one connecting hit does. comboIndex = 1 for the first hit of a combo.
function MovesRules.resolve(move: any, defender: Defender, comboIndex: number?): Outcome
	local kb = (type(move.knockback) == "table" and move.knockback) or { 0, 0, 0 }
	local knock = { num(kb[1], 0), num(kb[2], 0), num(kb[3], 0) }
	local base = math.max(0, num(move.damage, 0))
	local scale = math.max(0.4, 1 - COMBO_SCALING * (math.max(1, math.floor(num(comboIndex, 1))) - 1))
	local out: Outcome = {
		kind = "hit",
		damage = base * scale,
		stun = math.max(0, num(move.stun, 0)),
		hitstop = math.clamp(num(move.hitstop, 0.05), 0, 0.5),
		knockback = knock,
		attackerStun = 0,
	}
	if defender.iframes then
		out.kind, out.damage, out.stun, out.knockback = "dodged", 0, 0, { 0, 0, 0 }
		return out
	end
	local parryable = move.parryable ~= false and move.block ~= "unblockable"
	if
		parryable
		and defender.parryAt
		and defender.now - defender.parryAt >= 0
		and defender.now - defender.parryAt <= PARRY_WINDOW
	then
		out.kind, out.damage, out.stun, out.knockback = "parried", 0, 0, { 0, 0, 0 }
		out.attackerStun = math.max(0.6, num(move.stun, 0) * 1.5)
		out.hitstop = math.max(out.hitstop, 0.12)
		return out
	end
	if defender.blocking and move.block ~= "unblockable" then
		local chip = move.block == "chip"
		out.kind = if chip then "chip" else "blocked"
		out.damage = if chip then out.damage * 0.2 else 0
		out.stun = math.max(0, num(move.blockstun, 0.25))
		out.knockback = { knock[1] * 0.3, 0, knock[3] * 0.3 }
		return out
	end
	return out
end

-- frames the attacker is ahead (+) or behind (-) after the move is blocked on its first active frame
function MovesRules.onBlock(move: any): number
	local tl = MovesRules.timeline(move)
	local blockstun = math.floor(num(move.blockstun, 0.25) * tl.fps + 0.5)
	return blockstun - (tl.active - 1 + tl.recovery)
end

-- problems with a move (names = every move's name in the set, for cancels)
function MovesRules.validate(move: any, names: { [string]: boolean }?): { string }
	local issues = {}
	local function bad(msg: string)
		table.insert(issues, msg)
	end
	if type(move) ~= "table" or type(move.name) ~= "string" then
		bad('a move needs a "name"')
		return issues
	end
	if type(move.frames) ~= "table" then
		bad('"frames": { fps, startup, active, recovery } (or "from_anim", resolved before validation)')
		return issues
	end
	local tl = MovesRules.timeline(move)
	if tl.total < 2 then
		bad("the move lasts under 2 frames")
	end
	local first, last = tl.startup, tl.startup + tl.active - 1
	for i, hb in move.hitboxes or {} do
		local fr = hb.frames
		if type(fr) ~= "table" or #fr ~= 2 then
			bad(`hitbox {i}: "frames": [from, to]`)
		elseif num(fr[1], -1) < first or num(fr[2], math.huge) > last then
			bad(
				`hitbox {i}: frames {fr[1]}..{fr[2]} are outside the active frames {first}..{last} (a hitbox before the swing lands or after it ends feels like a ghost hit)`
			)
		end
		local size = hb.size
		if
			type(size) ~= "table"
			or #size ~= 3
			or num(size[1], 0) <= 0
			or num(size[2], 0) <= 0
			or num(size[3], 0) <= 0
		then
			bad(`hitbox {i}: "size": [x, y, z] > 0`)
		elseif num(size[1], 0) * num(size[2], 0) * num(size[3], 0) > 2000 then
			bad(
				`hitbox {i}: {size[1]}x{size[2]}x{size[3]} studs is huge — an R6 is 2x5x1 (a whiff that hits from across the room)`
			)
		end
	end
	if (move.damage or 0) > 0 and #(move.hitboxes or {}) == 0 then
		bad("damage but no hitboxes")
	end
	if move.block ~= nil and move.block ~= "blockable" and move.block ~= "chip" and move.block ~= "unblockable" then
		bad('"block" is blockable | chip | unblockable')
	end
	-- THE WHOOSH LEADS THE HIT (the anime / fighting-game vocabulary): a swing cue starts 50-300 ms before the first
	-- active frame - later it lands on (or after) the impact and smears it, earlier it reads as a separate sound
	if (move.damage or 0) > 0 and tl.active > 0 then
		for i, cue in move.sfx or {} do
			local ev = if type(cue) == "table" and type(cue.event) == "string" then string.lower(cue.event) else ""
			local whoosh = (type(cue) == "table" and cue.role == "whoosh")
				or string.find(ev, "swing", 1, true) ~= nil
				or string.find(ev, "whoosh", 1, true) ~= nil
			if whoosh then
				local lead = (tl.startup - num(cue.frame, 0)) / tl.fps
				if lead < 0.05 or lead > 0.3 then
					bad(
						`sfx {i} "{cue.event}" starts {math.floor(lead * 1000 + 0.5)} ms before the first active frame: a whoosh LEADS the hit by 50-300 ms (frame {math.max(
							0,
							tl.startup - math.floor(0.12 * tl.fps + 0.5)
						)})`
					)
				end
			end
		end
	end
	-- RESPONSIVENESS (AAA gaps v2 C1): a move with a `tier` reaches its first active frame within that tier's budget -
	-- the press-to-hit time players feel (games/<Game>/anim_style.json startup_s; a proposal until the owner approves)
	local budget = ({ light = 0.3, medium = 0.5, heavy = 1.1 } :: any)[move.tier]
	if type(budget) == "number" and tl.startup / tl.fps > budget + 1e-6 then
		bad(
			`startup {math.floor(tl.startup / tl.fps * 1000 + 0.5)} ms is over the {move.tier} budget {budget * 1000} ms (the press-to-hit a player feels)`
		)
	end
	-- ON HIT, THE KNOCKDOWN AND ITS GET-UP (LIMITATIONS_FIXES_V4 8.3: "validate onHit.getUp"): Moves hands these to
	-- AnimRagdoll.knock as they are - a typo was a silent no-op (a body that never stands up the authored way)
	local oh = move.onHit
	if oh ~= nil and type(oh) ~= "table" then
		bad('"onHit" is a table ({ "sfx", "vfx", "shake", "knockdown", "getUp", "getUpBlend" })')
	elseif type(oh) == "table" then
		local kd = oh.knockdown
		if kd ~= nil and (type(kd) ~= "number" or kd ~= kd or kd < 0 or kd > 5) then
			bad(`"onHit.knockdown" is the seconds the body lies limp, 0..5 (got {tostring(kd)})`)
		end
		local gu = oh.getUp
		if gu ~= nil then
			if type(gu) ~= "table" then
				bad(
					'"onHit.getUp" is { "back": "<clip>", "front": "<clip>" } (the get-up for a body on its back / front)'
				)
			else
				for side, clip in gu do
					if side ~= "back" and side ~= "front" then
						bad(`"onHit.getUp.{tostring(side)}": only "back" and "front" (the side the body landed on)`)
					elseif type(clip) ~= "string" or clip == "" then
						bad(`"onHit.getUp.{side}" names a clip (got {tostring(clip)})`)
					end
				end
				if not (type(kd) == "number" and kd > 0) then
					bad('"onHit.getUp" with no "knockdown": no body ever falls, so none ever gets up')
				end
			end
		end
		local gb = oh.getUpBlend
		if gb ~= nil and (type(gb) ~= "number" or gb ~= gb or gb < 0 or gb > 2) then
			bad(`"onHit.getUpBlend" is seconds 0..2 (got {tostring(gb)})`)
		end
	end
	local c = move.cancel
	if type(c) == "table" then
		if num(c.from, -1) < 0 or num(c.to, -1) < num(c.from, 0) or num(c.to, 0) >= tl.total then
			bad(`cancel window {tostring(c.from)}..{tostring(c.to)} must sit inside the move (0..{tl.total - 1})`)
		end
		for _, into in c.into or {} do
			if names and not names[into] then
				bad(`cancels into "{into}", which is not a move of this set`)
			end
		end
	end
	return issues
end

return MovesRules
