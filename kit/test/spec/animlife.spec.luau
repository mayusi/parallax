-- animlife.spec.luau — THE LIFECYCLE OF THE RUNTIME LAYERS A CLIENT RUNS (the owner's limitations list, 2026-11-15,
-- A-R01): one layer of a kind per character, all stopped at a respawn or a leave, stood down while a ragdoll has the
-- body and brought back after (src/kit/AnimLife), and the client that calls the layers through it
-- (src/kit/client/AnimRoot.client.luau). Made-up layers that count their starts and stops: what a real Animator, a
-- real respawn and several watching clients do is Studio's to show.
local frk = require("../frk")
local fs = require("@lune/fs")
local test, check = frk.test, frk.check

local AnimLife = require("../../../src/kit/AnimLife")

-- a layer that counts: { started, stopped }, and its start function
local function layer(): ({ started: number, stopped: number }, () -> () -> ())
	local c = { started = 0, stopped = 0 }
	return c, function()
		c.started += 1
		return function()
			c.stopped += 1
		end
	end
end

return function()
	test.suite("the runtime layers of a client: one of a kind, stopped when the character is gone", function()
		test.case("a layer runs once per character; started again, the old one is stopped first", function()
			local life = AnimLife.new()
			local c, start = layer()
			check.truthy(life:start("A", "feet", start))
			check.truthy(life:running("A", "feet") and life:count() == 1)
			check.truthy(life:start("A", "feet", start)) -- the character was seen twice
			check.truthy(c.started == 2 and c.stopped == 1 and life:count() == 1)
			-- another character has its own
			life:start("B", "feet", start)
			check.truthy(c.started == 3 and c.stopped == 1 and life:count() == 2)
			life:stop("A", "feet")
			check.truthy(c.stopped == 2 and not life:running("A", "feet") and life:running("B", "feet"))
			life:stop("A", "feet") -- stopping what does not run is nothing
			life:stop("Nobody", "feet")
			check.equal(c.stopped, 2)
		end)
		test.case("a respawn or a leave stops every layer of that character and forgets them", function()
			local life = AnimLife.new()
			local feet, startFeet = layer()
			local sway, startSway = layer()
			life:start("A", "feet", startFeet, { suspends = true })
			life:start("A", "secondary", startSway)
			life:start("B", "feet", startFeet, { suspends = true })
			life:clear("A")
			check.truthy(feet.stopped == 1 and sway.stopped == 1 and life:count() == 1)
			life:clear("A") -- twice (Destroying and the ancestry both fire): nothing more
			check.truthy(feet.stopped == 1 and sway.stopped == 1)
			-- nothing of the old character comes back: resuming it starts nothing
			life:resume("A", "down")
			check.equal(feet.started, 2)
			-- a character that left while it was down does not come back either
			life:suspend("B", "down")
			life:clear("B")
			life:resume("B", "down")
			check.truthy(feet.started == 2 and feet.stopped == 2 and life:count() == 0)
		end)
		test.case("a layer that fails to start, or whose stop throws, takes nothing else down", function()
			local life = AnimLife.new()
			local c, start = layer()
			check.truthy(not life:start("A", "broken", function()
				error("no such motion set")
			end))
			check.truthy(not life:running("A", "broken") and #life.errors == 1)
			check.truthy(string.find(life.errors[1], "starting broken", 1, true) ~= nil)
			life:start("A", "thrower", function()
				return function()
					error("already destroyed")
				end
			end)
			life:start("A", "feet", start)
			life:clear("A")
			check.truthy(c.stopped == 1 and life:count() == 0 and #life.errors == 2)
			-- a layer with nothing to stop (it found nothing to do) is simply not running
			check.truthy(not life:start("A", "nothing", function()
				return nil
			end))
			check.equal(life:count(), 0)
		end)
	end)

	test.suite("the runtime layers of a client: stood down while the body is not the animation's own", function()
		test.case(
			"a ragdoll stops the layers that stand down and leaves the others; getting up brings them back",
			function()
				local life = AnimLife.new()
				local feet, startFeet = layer()
				local sway, startSway = layer()
				life:start("A", "feet", startFeet, { suspends = true })
				life:start("A", "secondary", startSway)
				life:suspend("A", "down")
				check.truthy(feet.stopped == 1 and sway.stopped == 0)
				check.truthy(not life:running("A", "feet") and life:running("A", "secondary"))
				life:suspend("A", "down") -- the state changes again while down (FallingDown -> Ragdoll): once is once
				check.equal(feet.stopped, 1)
				life:resume("A", "down")
				check.truthy(feet.started == 2 and life:running("A", "feet"))
				life:resume("A", "down") -- up again and again: nothing is started twice
				check.truthy(feet.started == 2 and feet.stopped == 1)
			end
		)
		test.case("two reasons at once: the layers come back when the LAST one is gone", function()
			local life = AnimLife.new()
			local feet, startFeet = layer()
			life:start("A", "feet", startFeet, { suspends = true })
			life:suspend("A", "down")
			life:suspend("A", "cutscene")
			life:resume("A", "down")
			check.truthy(feet.started == 1 and not life:running("A", "feet"))
			life:resume("A", "cutscene")
			check.truthy(feet.started == 2 and life:running("A", "feet"))
		end)
		test.case("a layer asked for while the body is down waits; one stopped while down stays stopped", function()
			local life = AnimLife.new()
			local motion, startMotion = layer()
			local feet, startFeet = layer()
			life:suspend("A", "down") -- (down before anything was started: a character that spawns knocked over)
			check.truthy(not life:start("A", "motion", startMotion, { suspends = true }))
			check.equal(motion.started, 0)
			life:start("A", "feet", startFeet, { suspends = true })
			life:stop("A", "feet") -- the game turned it off meanwhile
			life:resume("A", "down")
			check.truthy(motion.started == 1 and life:running("A", "motion"))
			check.truthy(feet.started == 0 and not life:running("A", "feet"))
		end)
		test.case("which states take the body: a ragdoll, a knockdown, death - not a jump, a fall or a swim", function()
			-- (GettingUp: the get-up blend still writes the hips - the layers come back after it)
			for _, name in { "Physics", "Ragdoll", "FallingDown", "PlatformStanding", "GettingUp", "Dead" } do
				check.truthy(AnimLife.isDown(name))
			end
			for _, name in { "Running", "Jumping", "Freefall", "Landed", "Swimming", "Climbing", "Seated", "" } do
				check.truthy(not AnimLife.isDown(name))
			end
		end)
	end)

	test.suite("the runtime layers of a client: a start that waits", function()
		-- a start that YIELDS (it waits for a part, a module) and hands its stop back later
		local function waiting(): ({ started: number, stopped: number, go: () -> () }, () -> () -> ())
			local c = { started = 0, stopped = 0, go = function() end }
			return c,
				function()
					local me = coroutine.running()
					c.go = function()
						coroutine.resume(me)
					end
					coroutine.yield()
					c.started += 1
					return function()
						c.stopped += 1
					end
				end
		end
		test.case("the character went while its layer was starting: the layer is stopped as it arrives", function()
			local life = AnimLife.new()
			local c, start = waiting()
			coroutine.wrap(function()
				life:start("A", "effects", start)
			end)()
			life:clear("A") -- (destroyed during the wait)
			c.go()
			check.truthy(c.started == 1 and c.stopped == 1 and life:count() == 0)
		end)
		test.case("the body went down, or the layer was started again, during the wait: one layer at most", function()
			local life = AnimLife.new()
			local c, start = waiting()
			coroutine.wrap(function()
				life:start("A", "feet", start, { suspends = true })
			end)()
			life:suspend("A", "down")
			c.go()
			check.truthy(c.started == 1 and c.stopped == 1 and not life:running("A", "feet"))
			-- started again while the first start still waits: the first is stopped as it arrives, the second runs
			local life2 = AnimLife.new()
			local first, startFirst = waiting()
			local second, startSecond = layer()
			coroutine.wrap(function()
				life2:start("A", "motion", startFirst)
			end)()
			life2:start("A", "motion", startSecond)
			first.go()
			check.truthy(first.stopped == 1 and second.started == 1 and second.stopped == 0 and life2:count() == 1)
		end)
	end)

	test.suite("the runtime layers of a client: the client calls them through the rule", function()
		test.case(
			"feet, the motion set, secondary motion, the get-up watch and the effects, with their ends",
			function()
				local client = fs.readFile("src/kit/client/AnimRoot.client.luau")
				for _, line in
					{
						"local life = AnimLife.new()",
						"if watched[character] then",
						"character.Destroying:Once(over)",
						'life:start(character, "secondary", function()',
						'life:start(character, "getup", function()',
						'life:start(character, "effects", function()',
						'life:start(character, "feet", function()',
						'life:start(character, "motion", function()',
						"Crowd.track(character)",
						"Crowd.untrack(character)",
						"local stop = Anim.feet(character, {",
						"return Anim.motion(hum, set, { steer = if character == player.Character then true else nil })",
						"local mine = character == player.Character or Players:GetPlayerFromCharacter(character) == nil",
						'if mine and type(set) == "string" and set ~= "" then',
						'character:GetAttributeChangedSignal("KitMotionSet"):Connect(motion)',
						"if AnimLife.isDown(new.Name) then",
						'life:suspend(character, "down")',
						'life:resume(character, "down")',
						'hum:GetPropertyChangedSignal("PlatformStand"):Connect(platform)',
						'life:suspend(character, "out")',
						'CollectionService:GetInstanceAddedSignal("KitCharacter"):Connect(function(npc)',
						"p.CharacterRemoving:Connect(function(character)",
					}
				do
					check.truthy(string.find(client, line, 1, true) ~= nil)
				end
				-- the end is hooked BEFORE anything waits, and the layer that may wait longest starts last
				local hooked = string.find(client, "character.Destroying:Once(over)", 1, true) :: number
				local waits = string.find(client, 'character:WaitForChild("Humanoid", 10)', 1, true) :: number
				local feet = string.find(client, 'life:start(character, "feet", function()', 1, true) :: number
				local fx = string.find(client, 'life:start(character, "effects", function()', 1, true) :: number
				check.truthy(hooked < waits and waits < feet and feet < fx)
				-- feet and the motion set stand down for a ragdoll; the get-up watch and secondary motion do not
				local _, standDown = string.gsub(client, "{ suspends = true }", "")
				check.equal(standDown, 2)
			end
		)
	end)
end
