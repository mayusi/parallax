-- bus.spec.luau — the presentation event bus (src/kit/Bus): listeners in order, isolated from each other, "*" hears
-- all, once / stop work, a listener added mid-emit waits for the next event, `near` picks the audience.
local frk = require("../frk")
local test, check = frk.test, frk.check

local Bus = require("../../../src/kit/Bus")

-- a stand-in Vector3: a - b and .Magnitude (Lune has no Roblox datatypes)
local V = {}
V.__index = function(v, k)
	if k == "Magnitude" then
		return math.sqrt(v.x * v.x + v.y * v.y + v.z * v.z)
	end
	return nil
end
V.__sub = function(a, b)
	return setmetatable({ x = a.x - b.x, y = a.y - b.y, z = a.z - b.z }, V)
end
local function vec(x, y, z)
	return setmetatable({ x = x, y = y, z = z }, V)
end
local function player(name, pos)
	local root = { Position = pos }
	return {
		Name = name,
		Character = {
			FindFirstChild = function(_, n)
				return if n == "HumanoidRootPart" then root else nil
			end,
		},
	}
end

return function()
	test.suite("Bus", function()
		test.case("listeners run in order, then the '*' listeners, with the payload and the name", function()
			local b = Bus.new()
			local heard = {}
			b:on("*", function(_, name)
				table.insert(heard, "*" .. name)
			end)
			b:on("Hit", function(p)
				table.insert(heard, "a" .. p.damage)
			end)
			b:on("Hit", function(p)
				table.insert(heard, "b" .. p.damage)
			end)
			b:emit("Hit", { damage = 12 })
			b:emit("Death", {})
			check.equal(table.concat(heard, ","), "a12,b12,*Hit,*Death")
		end)
		test.case("a listener that errors is reported and the others still run", function()
			local reports = {}
			local b = Bus.new(function(text)
				table.insert(reports, text)
			end)
			local after = false
			b:on("Hit", function()
				error("boom")
			end)
			b:on("Hit", function()
				after = true
			end)
			b:emit("Hit", {})
			check.is_true(after)
			check.equal(#reports, 1)
			check.is_true(string.find(reports[1], '"Hit" listener failed', 1, true) ~= nil)
		end)
		test.case("stop and once; a listener added mid-emit hears the next event", function()
			local b = Bus.new()
			local n, once, late = 0, 0, 0
			local stop = b:on("Hit", function()
				n += 1
			end)
			b:once("Hit", function()
				once += 1
			end)
			b:on("Hit", function()
				b:on("Hit", function()
					late += 1
				end)
			end)
			b:emit("Hit", {})
			check.equal(late, 0)
			stop()
			b:emit("Hit", {})
			check.equal(n, 1)
			check.equal(once, 1)
			check.equal(late, 1)
		end)
		test.case("near: only players within that many studs of the event", function()
			local ps =
				{ player("close", vec(10, 0, 0)), player("far", vec(500, 0, 0)), { Name = "dead", Character = nil } }
			local got = Bus.audience(ps, vec(0, 0, 0), 120)
			check.equal(#got, 1)
			check.equal(got[1].Name, "close")
			check.equal(#Bus.audience(ps, nil, 120), 3) -- (no place: everyone)
		end)
		test.case("publish outside a server still tells the local listeners", function()
			local heard = nil
			local stop = Bus.on("Parried", function(p)
				heard = p.move
			end)
			Bus.publish("Parried", { move = "Jab" })
			stop()
			check.equal(heard, "Jab")
		end)
	end)
end
