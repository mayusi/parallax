-- __NAME__Controller.client.luau — input + feedback for __NAME__. Cosmetic only: it ASKS the server.
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local UserInputService = game:GetService("UserInputService")

local Shared = ReplicatedStorage:WaitForChild("Shared")
local __NAME__Config = require(Shared:WaitForChild("__NAME__Config"))

local player = Players.LocalPlayer
local mouse = player:GetMouse()
local request = ReplicatedStorage:WaitForChild(__NAME__Config.REQUEST) :: RemoteEvent
local reply = ReplicatedStorage:WaitForChild(__NAME__Config.REPLY) :: RemoteEvent
local key = (Enum.KeyCode :: any)[__NAME__Config.KEY]

UserInputService.InputBegan:Connect(function(input: InputObject, processed: boolean)
	if processed or not __NAME__Config.ENABLED or input.KeyCode ~= key then
		return
	end
	request:FireServer(mouse.Hit.Position, 5)
end)

reply.OnClientEvent:Connect(function(ok: unknown, message: unknown)
	print(`[__NAME__] {if ok then "ok" else "denied"}: {tostring(message)}`)
end)
