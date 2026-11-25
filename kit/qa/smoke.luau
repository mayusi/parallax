-- runs on: Server
-- smoke.luau (kit built-in) — the game boots: a player spawns alive, the kit runtime loaded, no instance explosion.
return function(t)
	local player = t.player(20)
	if not t.check("a player spawned with a character", player ~= nil) then
		return
	end
	local humanoid = player.Character:FindFirstChildOfClass("Humanoid")
	t.check("humanoid is alive", humanoid and humanoid.Health > 0, humanoid and humanoid.Health)
	local kit = t.find("ReplicatedStorage.kit")
	t.check(
		"kit runtime replicated (ReplicatedStorage.kit)",
		kit ~= nil,
		nil,
		"sync the project into Studio: run `rojo serve` and click Connect in the Rojo plugin"
	)
	local before = #workspace:GetDescendants()
	t.wait(3)
	local after = #workspace:GetDescendants()
	t.check(`workspace stable while idle ({before} -> {after})`, after - before < 500, after - before)
end
