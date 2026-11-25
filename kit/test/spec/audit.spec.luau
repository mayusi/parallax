-- audit.spec.luau (kit) — the security audit catches the exploit classes it claims to and stays quiet on safe code.
local frk = require("../frk")
local test, check = frk.test, frk.check

local Audit = require("../../lib/audit")

local function rules(src: string, isServer: boolean?): { [string]: number }
	local out = {}
	for _, f in Audit.scan("x.luau", src, isServer ~= false) do
		local key = f.rule .. ":" .. f.severity
		out[key] = (out[key] or 0) + 1
	end
	return out
end

local SAFE = [[
local limit = RateLimit.new(3, 1)
remote.OnServerEvent:Connect(function(player, rawTarget, rawPower)
	if not limit:take(player.UserId, os.clock()) then return end
	local ok, target = Guard.vector3(rawTarget)
	if not ok then return end
	local okRules = Rules.check(rawPower, 10)
	if typeof(target) == "Vector3" then print(target) end
end)
]]

return function()
	test.suite("Audit: safe code passes", function()
		test.case("validated + rate-limited handler has no findings", function()
			check.equal(next(rules(SAFE)), nil)
		end)
		test.case("keywords inside strings and comments are ignored", function()
			local src = 'print("OnServerEvent loadstring( require(123)") -- InvokeClient( getfenv(\n--[[ require(99) ]]'
			check.equal(next(rules(src)), nil)
		end)
		test.case("unused client args are fine", function()
			local src =
				"r.OnServerEvent:Connect(function(player, _unused)\n\tif os.clock() then print(player) end\nend)"
			check.equal(next(rules(src)), nil)
		end)
	end)

	test.suite("Audit: catches exploits", function()
		test.case("unvalidated client argument", function()
			local src =
				"r.OnServerEvent:Connect(function(player, amount)\n\tlocal last = os.clock()\n\tplayer.leaderstats.Coins.Value += amount\nend)"
			check.equal(rules(src)["remote-arg:error"], 1)
		end)
		test.case("named handler is followed", function()
			local src =
				"local function onHit(player, dmg)\n\tif os.clock() then hum:TakeDamage(dmg) end\nend\nr.OnServerEvent:Connect(onHit)"
			check.equal(rules(src)["remote-arg:error"], 1)
		end)
		test.case("OnServerInvoke assignment", function()
			local src = "rf.OnServerInvoke = function(player, item)\n\treturn shop[item]\nend"
			local r = rules(src)
			check.equal(r["remote-arg:error"], 1)
			check.equal(r["no-rate-limit:warn"], 1)
		end)
		test.case("missing rate limit warns", function()
			local src = "r.OnServerEvent:Connect(function(player, n)\n\tif type(n) ~= 'number' then return end\nend)"
			check.equal(rules(src)["no-rate-limit:warn"], 1)
		end)
		test.case("nested blocks don't end the handler early", function()
			local src =
				"r.OnServerEvent:Connect(function(player, a)\n\tif os.clock() then\n\t\tfor i = 1, 2 do\n\t\t\tprint(i)\n\t\tend\n\telseif true then\n\t\tprint(1)\n\tend\n\tuse(a)\nend)"
			check.equal(rules(src)["remote-arg:error"], 1)
		end)
		test.case("backdoor require(id), loadstring, InvokeClient, fenv", function()
			local r = rules("require(4815162342)\nloadstring(src)()\nrf:InvokeClient(p)\nsetfenv(1, {})")
			check.equal(r["require-id:error"], 1)
			check.equal(r["loadstring:error"], 1)
			check.equal(r["invoke-client:error"], 1)
			check.equal(r["fenv:warn"], 1)
		end)
		test.case("InvokeClient is only an error on the server", function()
			check.equal(rules("rf:InvokeClient(p)", false)["invoke-client:error"], nil)
		end)
		test.case("FireAllClients in a loop", function()
			check.equal(rules("for _, p in list do\n\tremote:FireAllClients(p)\nend")["fire-all-loop:warn"], 1)
		end)
	end)
end
