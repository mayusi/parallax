# The audience of a broadcast, proven in ONE Studio play session (F-R03)

The Studio tools start one play client, so "two clients" is proven with ONE player who is moved: far away (must get
nothing), into reach while the effect still lasts (must get it late and catch up), near (must get it at once), and
into reach after the effect is over (must get nothing). TWO players at once are proven by `two_players.md` beside
this file (a local server Studio starts from a script). What this one does NOT prove: two observers at the same moment,
and whether an effect leads or trails the attacker another player sees.

Place: the kit's own scratch place (`build/vfx/studio/scratch.project.json`, with
`StarterPlayer.StarterPlayerScripts.VfxClient` = `src/kit/client/VfxClient.client.luau` so the real receiver runs).
Never a game's place; nothing saved, nothing uploaded. Start play, then run the CLIENT part once, the SERVER part
once, then the CLIENT READ.

## CLIENT (datamodel: Client) - count what arrives, and how late

```lua
local RS = game:GetService("ReplicatedStorage")
local Vfx = require(RS.kit.Vfx)
local remote = RS:WaitForChild(Vfx.REMOTE_NAME)
shared.kitGot = {}
remote.OnClientEvent:Connect(function(name, _where, _scale, _target, sent)
	table.insert(shared.kitGot, { name = name, late = workspace:GetServerTimeNow() - (sent or 0), at = os.clock() })
end)
return "listening on " .. Vfx.REMOTE_NAME
```

## SERVER (datamodel: Server) - move the one player, broadcast, say what was sent

```lua
local RS = game:GetService("ReplicatedStorage")
local Players = game:GetService("Players")
local Vfx = require(RS.kit.Vfx)
local NAME = "getsuga_tensho_v2" -- 3.6 s; its rule reach is under 1000 studs
local player = Players:GetPlayers()[1]
local character = player.Character or player.CharacterAdded:Wait()
local root = character:WaitForChild("HumanoidRootPart")
local function stand(x)
	root.Anchored = true
	character:PivotTo(CFrame.new(x, 10, 0))
	task.wait(0.3)
end
local out = { length = Vfx.realLengthOf(NAME) }
stand(5000)
out.far = Vfx.broadcast(NAME, Vector3.new(0, 3, 0)) -- expect 0
task.wait(1.0)
stand(40) -- walks into reach 1.3 s into a 3.6 s effect: the watch must send it within 0.25 s
task.wait(0.7)
out.walkedIn = "see the client: one event about 1.3 to 1.6 s late"
task.wait(out.length) -- let it end
out.near = Vfx.broadcast(NAME, Vector3.new(0, 3, 0)) -- expect 1, at once
task.wait(out.length + 0.5)
stand(5000)
out.farAgain = Vfx.broadcast(NAME, Vector3.new(0, 3, 0)) -- expect 0
task.wait(out.length + 0.5) -- it is over
stand(40) -- into reach AFTER it ended: nothing may be sent
task.wait(1.0)
out.everyone = Vfx.broadcast(NAME, Vector3.new(0, 3, 0), 1, nil, { reach = false }) -- expect 1: everyone
root.Anchored = false
return game:GetService("HttpService"):JSONEncode(out)
```

## CLIENT READ (datamodel: Client)

```lua
local VfxMesh = require(game:GetService("ReplicatedStorage").kit.VfxMesh)
return game:GetService("HttpService"):JSONEncode({ got = shared.kitGot, meshesNow = VfxMesh.stats().active })
```

## What must come back

- SERVER: `far = 0`, `near = 1`, `farAgain = 0`, `everyone = 1`.
- CLIENT: exactly THREE events - the walk-in (late between 1.2 and 1.7 s), the near one (late under 0.3 s), the
  `reach = false` one (late under 0.3 s). No event for the first far broadcast before the walk-in, none for the
  second far broadcast (the player came into reach after it was over).
- A fourth event, or a walk-in that is not late, is a fault in `Vfx.broadcast` / `VfxNet.newcomers`.
