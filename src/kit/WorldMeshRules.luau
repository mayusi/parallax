--!strict
-- WorldMeshRules.luau (kit) — the RULES of a world's meshes at runtime (pure: no services, no instances; the
-- swapper WorldMeshes.luau acts on them, kit/test/spec/worldmeshes.spec.luau holds them).
--
-- Two things a mesh that does not arrive must never do (the owner's limitations list, W-R01 and W-R02):
--   * take a surface or an obstacle out of the game in silence. The compiler's placeholder is an invisible part
--     that does not collide; before these rules a rock or a cliff whose mesh was not uploaded, was moderated or
--     failed to load stayed exactly that - you walked through where the map said stone. And whatever stands on
--     its own unseen collision behind a mesh - a house in a skin or a facade, a castle wall of modules, a mesh
--     tower's top, a mesh tree's trunk - stayed that unseen collision: you bumped into nothing you could see.
--   * stay failed for the whole session because ONE call failed. A failed load was cached as "never" on its first
--     error; a hiccup at server start cost every copy of that mesh until the server closed.
local Rules = {}

Rules.TRIES = 3 -- loads tried in one round
Rules.BACKOFF = { 1, 3 } -- seconds before the 2nd and the 3rd try of a round
Rules.COOLDOWN = 30 -- seconds after a failed round before the next round begins
Rules.ROUNDS = 4 -- rounds a session: after 12 failures the mesh is given up (a moderated asset never loads)

export type Load = { fails: number, failedAt: number?, ok: boolean? }

function Rules.new(): Load
	return { fails = 0 }
end

-- what to do about a mesh now: "have" | "try" | "wait" (and the seconds left) | "given up"
function Rules.attempt(state: Load, now: number): (string, number?)
	if state.ok then
		return "have", nil
	end
	if state.fails >= Rules.TRIES * Rules.ROUNDS then
		return "given up", nil
	end
	if state.fails == 0 or state.failedAt == nil then
		return "try", nil
	end
	local inRound = state.fails % Rules.TRIES
	local wait = if inRound == 0 then Rules.COOLDOWN else Rules.BACKOFF[inRound]
	local left = wait - (now - state.failedAt)
	if left <= 0 then
		return "try", nil
	end
	return "wait", left
end

function Rules.failed(state: Load, now: number)
	state.fails += 1
	state.failedAt = now
end

function Rules.loaded(state: Load)
	state.ok = true
end

-- WHAT STANDS IN for a placeholder whose mesh is not there (not uploaded, failed, given up):
--   a SOLID thing (a rock, a cliff, a wall: its placeholder says Collide) is its own box, seen and solid - a plain
--     block where the map says stone, never a hole in the world;
--   a thing that DRESSES unseen collision (a skin, a facade module, a castle wall's module, a mesh tower, a mesh
--     tree: the compiler names what each hides) shows nothing itself - what it hides is shown instead (`blockout`):
--     the building's own walls and roof, the wall's own blocks, the tree's trunk;
--   anything else (a fern, a mesh with no collision of its own) stays unseen: it was never an obstacle.
-- ph: { collide: boolean, dress: string? } -> { show: boolean, collide: boolean, blockout: string? }
function Rules.standIn(ph: any): any
	if type(ph.dress) == "string" and ph.dress ~= "" then
		return { show = false, collide = false, blockout = ph.dress }
	end
	if ph.collide == true then
		return { show = true, collide = true }
	end
	return { show = false, collide = false }
end

-- a building is DRESSED only when every mesh that dresses it is there: one missing module and the whole building
-- shows its own walls (half a facade over nothing reads as a ruin; modules over shown walls flicker in one plane).
-- states: { [meshKey]: "have" | anything else } for the building's meshes -> true = dressed
function Rules.dressed(states: { string }): boolean
	if #states == 0 then
		return false
	end
	for _, st in states do
		if st ~= "have" then
			return false
		end
	end
	return true
end

-- A MESH'S COLLISION SHAPE AND LEVEL OF DETAIL (LIMITATIONS_FIXES_V3.md stage B.2): a MeshPart's CollisionFidelity and
-- RenderFidelity are fixed when it is created, so they are asked for in CreateMeshPartAsync's options (seen in Studio,
-- 2026-11-17, card fbvv: taken exactly as asked; a key Roblox does not know is refused). Before this every world mesh
-- was created with Roblox's defaults: a fern, a leaf card or a house's skin - none of which collides - carried a full
-- decomposed collision shape. The rule: a mesh that does not collide asks for a Box (the cheapest, never touched),
-- one that collides for Roblox's Default (its shape, concave parts kept: a cliff's overhang, an arch); every mesh
-- Automatic detail (Roblox lowers it with distance).
-- -> collision, render (Roblox's enum names)
function Rules.fidelity(collide: boolean): (string, string)
	return if collide then "Default" else "Box", "Automatic"
end

-- one load (and one template) per mesh id AND pair of settings: the same rock collides here and is a far backdrop
-- there
function Rules.key(meshId: string, collision: string, render: string): string
	return `{meshId}|{collision}|{render}`
end

-- is the world ready to be played in: nothing still to try (every mesh is there, has a stand-in for good, or was
-- never uploaded). counts: { pending: number }
function Rules.ready(counts: any): boolean
	return (counts.pending or 0) == 0
end

return Rules
