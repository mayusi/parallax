-- SfxClient — plays the sounds the server broadcasts (ReplicatedStorage.kit.Sfx). Kit-owned.
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Sfx = require(ReplicatedStorage:WaitForChild("kit"):WaitForChild("Sfx"))
Sfx.startClient()
