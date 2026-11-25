-- runs on: Server
-- __name__.luau — playtest scenario. First line picks the datamodel: "-- runs on: Server" (assert game state,
-- call server code) or "-- runs on: Client" (fire remotes like a real player, read the UI).
-- Run: lune run kit playtest bundle __name__   (then follow the printed Studio MCP steps)
-- t.check(name, cond, detail?) · t.wait(s) · t.waitFor(fn, timeout?) · t.player(timeout?) · t.find("A.B.C")
return function(t)
	local player = t.player()
	if not t.check("player spawned", player ~= nil) then
		return
	end
	-- Example: assert something your feature guarantees, e.g. a remote exists
	-- t.check("DashRequest remote exists", t.find("ReplicatedStorage.DashRequest") ~= nil)
end
