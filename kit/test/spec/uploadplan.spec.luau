-- uploadplan.spec.luau (kit) — `kit upload`'s Studio route without an API key (kit/lib/uploadplan.luau): the exact
-- open_cloud_invoke arguments the Roblox Studio MCP takes for a file, the experience grant, the strict asset id an agent
-- hands back, and a file named relative or absolute, any slash, any drive-letter case.
local serde = require("@lune/serde")

local frk = require("../frk")
local test, check = frk.test, frk.check

local UploadPlan = require("../../lib/uploadplan")

local CWD = "C:\\Games\\MyGame\\"

return function()
	test.suite("upload plan: the Studio MCP route (no API key)", function()
		test.case(
			"one file's open_cloud_invoke call: the Assets API request as an object, the file by absolute path",
			function()
				local job = { file = "build/textures/spark.png", assetType = "Image", name = "MyGame-spark" }
				local c = UploadPlan.call(job, { userId = "42" }, CWD)
				check.equal(c.method, "POST")
				check.equal(c.endpoint, "/assets/v1/assets")
				local body = serde.decode("json", c.body)
				check.equal(body.request.assetType, "Image")
				check.equal(body.request.displayName, "MyGame-spark")
				check.equal(body.request.creationContext.creator.userId, "42")
				check.equal(#c.files, 1)
				check.equal(c.files[1].name, "fileContent")
				check.equal(c.files[1].path, "C:/Games/MyGame/build/textures/spark.png")
				check.equal(table.concat(c.scopes, ","), "asset:read,asset:write")
				local group = UploadPlan.call(job, { groupId = "7" }, "/home/me/game")
				check.equal(serde.decode("json", group.body).request.creationContext.creator.groupId, "7")
				check.equal(group.files[1].path, "/home/me/game/build/textures/spark.png")
			end
		)
		test.case("the experience grant names every id and its own scope", function()
			local g = UploadPlan.grant("99", { "1", "2" })
			check.equal(g.method, "PATCH")
			check.equal(g.endpoint, "/asset-permissions-api/v1/assets/permissions")
			local body = serde.decode("json", g.body)
			check.equal(body.subjectType, "Universe")
			check.equal(body.subjectId, "99")
			check.equal(body.action, "Use")
			check.equal(#body.requests, 2)
			check.equal(body.requests[2].assetId, "2")
			check.equal(g.scopes[1], "asset-permissions:write")
		end)
		test.case("an asset id is digits or rbxassetid://digits - never a string that merely ends in digits", function()
			check.equal(UploadPlan.assetId("123456"), "123456")
			check.equal(UploadPlan.assetId(" 123456 "), "123456")
			check.equal(UploadPlan.assetId("rbxassetid://987"), "987")
			check.equal(UploadPlan.assetId("operations/abc123"), nil)
			check.equal(UploadPlan.assetId("C:/Games/MyGame/build/a123"), nil)
			check.equal(UploadPlan.assetId("12a"), nil)
			check.equal(UploadPlan.assetId(""), nil)
			check.equal(UploadPlan.assetId(nil), nil)
		end)
		test.case("a file named relative or absolute, any slash, any drive-letter case, is one project path", function()
			check.equal(UploadPlan.relative("build/textures/a.png", CWD), "build/textures/a.png")
			check.equal(UploadPlan.relative("./build/textures/a.png", CWD), "build/textures/a.png")
			check.equal(UploadPlan.relative("build\\textures\\a.png", CWD), "build/textures/a.png")
			check.equal(UploadPlan.relative("C:/Games/MyGame/build/textures/a.png", CWD), "build/textures/a.png")
			check.equal(UploadPlan.relative("c:\\games\\mygame\\build\\textures\\a.png", CWD), "build/textures/a.png")
			check.equal(UploadPlan.relative("D:/Other/a.png", CWD), "D:/Other/a.png") -- (not this project's: no plan entry)
			check.equal(UploadPlan.absolute("build\\a.png", CWD), "C:/Games/MyGame/build/a.png")
		end)
	end)
end
