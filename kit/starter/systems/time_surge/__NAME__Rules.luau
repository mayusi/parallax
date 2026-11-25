-- __NAME__Rules.luau — the decisions of the __NAME__ system as PURE functions (unit-tested in tests/spec).
-- State per player: { activeUntil: number, readyAt: number } (server clock seconds). The server owns it.
local __NAME__Config = require("./__NAME__Config")

local __NAME__Rules = {}

export type State = { activeUntil: number, readyAt: number }

function __NAME__Rules.new(): State
	return { activeUntil = 0, readyAt = 0 }
end

function __NAME__Rules.isActive(state: State, now: number): boolean
	return now < state.activeUntil
end

-- may the player start the mode now?
function __NAME__Rules.canActivate(state: State, now: number): (boolean, string?)
	if not __NAME__Config.ENABLED then
		return false, "disabled"
	end
	if __NAME__Rules.isActive(state, now) then
		return false, "already active"
	end
	if now < state.readyAt then
		return false, `cooling down ({math.ceil(state.readyAt - now)} s)`
	end
	return true, nil
end

-- the state after activating at `now` (call only when canActivate said yes)
function __NAME__Rules.activate(_state: State, now: number): State
	local untilT = now + __NAME__Config.DURATION
	return { activeUntil = untilT, readyAt = untilT + __NAME__Config.COOLDOWN }
end

-- how much WalkSpeed to ADD on activation (removed again as the same amount, so other speed effects survive)
function __NAME__Rules.boost(current: number): number
	return math.max(0, current) * (__NAME__Config.SPEED_MULTIPLIER - 1)
end

return __NAME__Rules
