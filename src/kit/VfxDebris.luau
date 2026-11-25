--!strict
-- VfxDebris.luau (kit) — effect debris collides with the WORLD only (LIMITATIONS_FIXES_V4 VFX-X B9: '"VfxDebris"
-- WorldOnly collision group'). A fracture's chips and a slab's pieces fly on the engine's physics (VfxStage); before,
-- they were Default parts: they knocked into the players' characters (a chip shoving the local player), piled on
-- each other (dozens of pieces resolving against each other every step) and were hit by raycasts and touch events
-- (a hitbox or a footstep sensor reading a pebble).
--   setup()      SERVER (collision groups can only be registered there): the "VfxDebris" group collides with the
--                world (Default) but never with itself or with "KitCharacters"; every player's character parts still
--                in Default join KitCharacters (a game that set its own character group keeps it)
--   mark(part)   either side: the part leaves touch and queries, and joins VfxDebris once the server registered it
local PhysicsService = game:GetService("PhysicsService")
local Players = game:GetService("Players")

local VfxDebris = {}
VfxDebris.GROUP = "VfxDebris"
VfxDebris.CHARACTERS = "KitCharacters"

local function joinCharacters(part: Instance)
	if part:IsA("BasePart") and part.CollisionGroup == "Default" then
		part.CollisionGroup = VfxDebris.CHARACTERS
	end
end

local function tag(character: Model)
	for _, d in character:GetDescendants() do
		joinCharacters(d)
	end
	character.DescendantAdded:Connect(joinCharacters)
end

local ready = false
function VfxDebris.setup()
	if ready then
		return
	end
	ready = true
	for _, g in { VfxDebris.GROUP, VfxDebris.CHARACTERS } do
		if not PhysicsService:IsCollisionGroupRegistered(g) then
			PhysicsService:RegisterCollisionGroup(g)
		end
	end
	PhysicsService:CollisionGroupSetCollidable(VfxDebris.GROUP, VfxDebris.GROUP, false)
	PhysicsService:CollisionGroupSetCollidable(VfxDebris.GROUP, VfxDebris.CHARACTERS, false)
	local function watch(player: Player)
		if player.Character then
			tag(player.Character)
		end
		player.CharacterAdded:Connect(tag)
	end
	for _, p in Players:GetPlayers() do
		watch(p)
	end
	Players.PlayerAdded:Connect(watch)
end

function VfxDebris.mark(part: BasePart)
	part.CanTouch = false
	part.CanQuery = false
	if PhysicsService:IsCollisionGroupRegistered(VfxDebris.GROUP) then
		part.CollisionGroup = VfxDebris.GROUP
	end
end

return VfxDebris
