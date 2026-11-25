-- vfxdailies.luau (kit) — the last word of a recorded play (the VFX studio-route plan, V0, 2026-11-12).
-- Every `kit vfx play <name> --record` runs the dailies (kit/vfx/dailies.py: the recording beside its scene frame by
-- frame, every frame large) and its summary ENDS with `LOOK: <folder>`: a session read contact sheets of thumbnails
-- and never the motion, and had to think of asking for more. This is only the wording, kept apart so it is tested:
-- whatever the dailies step did - made the pages, failed, crashed - the play still ends by naming a folder of frames.
local VfxDailies = {}

-- base / nextAction: the play's own summary and next action; result: the dailies step's JSON line (nil = it crashed);
-- name: the recording's name (build/vfx/booth/<name>_play/ holds its frames). -> summary, next action
function VfxDailies.playReport(base: string, nextAction: string, result: any?, name: string): (string, string)
	local said = if type(result) == "table" and type(result.summary) == "string" then result.summary else nil
	if said and string.find(said, "LOOK: ", 1, true) then
		local next = if type(result.next_action) == "string" then result.next_action else nextAction
		return `{base}. {said}`, next
	end
	return `{base}. No dailies ({said or "the dailies step crashed"}). LOOK: build/vfx/booth/{name}_play/`,
		`open the recorded frames in build/vfx/booth/{name}_play/ at full size; then find out why there are no dailies: lune run kit vfx dailies {name}`
end

return VfxDailies
