-- animlook.spec.luau — the animation lane's LOOK in the kit's locks (kit/lib/lanelocks.luau lookProblem; card u8d6,
-- the owner's V3 list anim stage A.2): the lane's sheet (build/animations/<Name>.sheet/look.json) is a look - before,
-- only the old kit anim look gif counted, so a move whose sheet was made and looked at was still owed a look.
local frk = require("../frk")
local fs = require("@lune/fs")
local task = require("@lune/task")
local test, check = frk.test, frk.check

local LaneLocks = require("../../lib/lanelocks")

local NAME = "ZzSpecLookProbe"
local DIR = "build/animations"

local function clean()
	for _, f in { `{DIR}/{NAME}.clip.json`, `{DIR}/{NAME}.sheet/look.json` } do
		if fs.isFile(f) then
			fs.removeFile(f)
		end
	end
	if fs.isDir(`{DIR}/{NAME}.sheet`) then
		fs.removeDir(`{DIR}/{NAME}.sheet`)
	end
end

return function()
	test.suite("the animation lane's look (lanelocks.lookProblem)", function()
		test.case("a built clip with no look is owed one; the command named is the sheet", function()
			clean()
			fs.writeDir(DIR)
			fs.writeFile(`{DIR}/{NAME}.clip.json`, "{}")
			local problem, cmd, known = LaneLocks.lookProblem("anim", NAME)
			clean()
			check.truthy(known)
			check.truthy(problem ~= nil and string.find(problem :: string, "no anim look", 1, true) ~= nil)
			check.truthy(cmd ~= nil and string.find(cmd :: string, "kit anim sheet " .. NAME, 1, true) ~= nil)
		end)
		test.case("its sheet made after the clip is the look", function()
			clean()
			fs.writeDir(`{DIR}/{NAME}.sheet`)
			fs.writeFile(`{DIR}/{NAME}.clip.json`, "{}")
			task.wait(1.1) -- (file times: the sheet is newer than the clip it shows)
			fs.writeFile(`{DIR}/{NAME}.sheet/look.json`, "{}")
			local problem, _, known = LaneLocks.lookProblem("anim", NAME)
			clean()
			check.truthy(known)
			check.equal(problem, nil)
		end)
		test.case("a clip rebuilt after its sheet is owed a new look", function()
			clean()
			fs.writeDir(`{DIR}/{NAME}.sheet`)
			fs.writeFile(`{DIR}/{NAME}.sheet/look.json`, "{}")
			task.wait(1.1)
			fs.writeFile(`{DIR}/{NAME}.clip.json`, "{}")
			local problem = LaneLocks.lookProblem("anim", NAME)
			clean()
			check.truthy(problem ~= nil and string.find(problem :: string, "changed after", 1, true) ~= nil)
		end)
	end)
end
