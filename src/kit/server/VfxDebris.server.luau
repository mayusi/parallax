-- VfxDebris.server.luau (kit) — the effect-debris collision groups, registered when the server starts (src/kit/VfxDebris:
-- debris collides with the world, never with itself or with the players' characters).
local ReplicatedStorage = game:GetService("ReplicatedStorage")

require(ReplicatedStorage:WaitForChild("kit"):WaitForChild("VfxDebris")).setup()
