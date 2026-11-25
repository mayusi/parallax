-- models.spec.luau — built asset + uploaded ids -> the KitModels data Models.spawn reads.
local frk = require("../frk")
local test, check = frk.test, frk.check

local Models = require("../../lib/models")

local MANIFEST = {
	anchors = { Muzzle = { 0, 0.1, -3.2 } },
	groups = {
		glass = {
			fbx = "build/models/rifle_glass.fbx",
			textures = { color = "build/models/textures/rifle_glass_color.png" },
			size_studs = { 0.4, 0.4, 0.05 },
			center = { 0, 1.75, -0.99 },
			transparency = 0.6,
		},
		main = {
			fbx = "build/models/rifle.fbx",
			textures = {
				color = "build/models/textures/rifle_color.png",
				rough = "build/models/textures/rifle_rough.png",
				normal = "build/models/textures/rifle_normal.png",
				emissive = "build/models/textures/rifle_emissive.png",
			},
			size_studs = { 1, 2, 5 },
			center = { 0, 1, -0.4 },
			transparency = 0,
		},
	},
}

return function()
	test.suite("Models.unshippedAssets / isPrivateFile", function()
		test.case("private assets and masters never ship as built: their meshes and maps; nothing else", function()
			local private = Models.unshippedAssets({
				["gjallarhorn.manifest.json"] = { private = true },
				["crate.manifest.json"] = { groups = {} },
				["sword.manifest.json"] = { private = false },
				["blaster.manifest.json"] = { stage = "master" },
				["lamp.manifest.json"] = { stage = "game" },
			})
			check.equal(#private, 2)
			check.equal(private[1], "blaster")
			check.equal(private[2], "gjallarhorn")
			for _, stem in { "gjallarhorn", "gjallarhorn_drum", "gjallarhorn_color", "gjallarhorn_leg_rough" } do
				check.is_true(Models.isPrivateFile(stem, private))
			end
			for _, stem in { "crate", "crate_color", "gjallarhornet", "sword" } do
				check.is_false(Models.isPrivateFile(stem, private))
			end
		end)
	end)

	test.suite("Models.compile", function()
		test.case("every map lands on the SurfaceAppearance; main group comes first", function()
			local ids = {
				models = { rifle = "rbxassetid://1", rifle_glass = "rbxassetid://2" },
				textures = {
					rifle_color = "rbxassetid://3",
					rifle_rough = "rbxassetid://4",
					rifle_normal = "rbxassetid://5",
					rifle_emissive = "rbxassetid://6",
					rifle_glass_color = "rbxassetid://7",
				},
			}
			local model, missing = Models.compile("rifle", MANIFEST, ids)
			check.equal(#missing, 0)
			local main = model.children[1]
			check.equal(main.name, "main")
			check.equal(main.attributes.MeshId, "rbxassetid://1")
			check.equal(main.attributes.Center.Vector3[3], -0.4)
			local props = main.children[1].properties
			check.equal(props.ColorMap, "rbxassetid://3")
			check.equal(props.RoughnessMap, "rbxassetid://4")
			check.equal(props.NormalMap, "rbxassetid://5")
			check.equal(props.EmissiveMaskContent, "rbxassetid://6")
			check.equal(model.attributes.Anchor_Muzzle.Vector3[3], -3.2)
			local glass = model.children[2]
			check.equal(glass.attributes.Transparency, 0.6)
		end)
		test.case("a group whose map cuts its outline is marked for the cut-out mode, no other is", function()
			local cut = table.clone(MANIFEST)
			cut.groups = table.clone(MANIFEST.groups)
			cut.groups.main = table.clone(MANIFEST.groups.main)
			cut.groups.main.alpha_mode = "Transparency"
			local ids = { models = { rifle = "rbxassetid://1", rifle_glass = "rbxassetid://2" } }
			local model = Models.compile("rifle", cut, ids)
			check.equal(model.children[1].children[1].properties.AlphaMode, "Transparency")
			check.equal(model.children[2].children[1].properties.AlphaMode, nil)
			local plain = Models.compile("rifle", MANIFEST, ids)
			check.equal(plain.children[1].children[1].properties.AlphaMode, nil)
		end)
		test.case("a group that fades by degrees is given a hair of transparency so the engine blends", function()
			local soft = table.clone(MANIFEST)
			soft.groups = table.clone(MANIFEST.groups)
			soft.groups.main = table.clone(MANIFEST.groups.main)
			soft.groups.main.alpha_mode = "Transparency"
			soft.groups.main.alpha_soft = true
			local ids = { models = { rifle = "rbxassetid://1", rifle_glass = "rbxassetid://2" } }
			local model = Models.compile("rifle", soft, ids)
			check.equal(model.children[1].attributes.Transparency, 0.02)
			check.equal(model.children[1].children[1].properties.AlphaMode, "Transparency")
			check.equal(model.children[2].attributes.Transparency, 0.6) -- (the glass keeps its own)
			local plain = Models.compile("rifle", MANIFEST, ids)
			check.equal(plain.children[1].attributes.Transparency, 0)
		end)
		test.case("a follower joint and a chain of joints are carried for the game to pose", function()
			local rig = table.clone(MANIFEST)
			rig.joints = {
				Shoulder = {
					group = "main",
					kind = "hinge",
					axis = { 0, 0, 1 },
					pivot = { 0, 1, 0 },
					min = -90,
					max = 90,
				},
				Wrist = {
					group = "glass",
					kind = "hinge",
					parent = "main",
					axis = { 0, 0, 1 },
					pivot = { 0, 3, 0 },
					min = -90,
					max = 90,
					follows = { joint = "Shoulder", ratio = -1, offset = 0 },
				},
			}
			rig.chains = { Arm = { joints = { "Shoulder", "Wrist" }, tip = { 0, 4, 0 }, span = 3, poses = {} } }
			local ids = { models = { rifle = "rbxassetid://1", rifle_glass = "rbxassetid://2" } }
			local model = Models.compile("rifle", rig, ids)
			check.equal(model.children[2].attributes.JointFollows, "Shoulder")
			check.equal(model.children[2].attributes.JointRatio, -1)
			check.equal(model.children[1].attributes.JointFollows, nil)
			local chains = nil
			for _, child in model.children do
				if child.name == "Chains" then
					chains = child
				end
			end
			check.is_true(chains ~= nil)
			check.equal(chains.children[1].name, "Arm")
			check.is_true(string.find(chains.children[1].properties.Value, '"Shoulder"', 1, true) ~= nil)
			rig.chains = { Arm = { joints = { "Shoulder", "Nope" }, tip = { 0, 4, 0 } } } -- a joint that is not there
			local ok, why = pcall(Models.compile, "rifle", rig, ids)
			check.is_false(ok)
			check.is_true(string.find(tostring(why), 'names the joint "Nope"', 1, true) ~= nil)
		end)
		test.case("a broken part's whole and its pieces are marked, and no other group is", function()
			local broken = table.clone(MANIFEST)
			broken.fracture = { Body = { whole = "main", groups = { "glass" }, held = 1 } }
			local ids = { models = { rifle = "rbxassetid://1", rifle_glass = "rbxassetid://2" } }
			local model = Models.compile("rifle", broken, ids)
			check.equal(model.children[1].attributes.Whole, "Body")
			check.equal(model.children[1].attributes.Shard, nil)
			check.equal(model.children[2].attributes.Shard, "Body")
			local plain = Models.compile("rifle", MANIFEST, ids)
			check.equal(plain.children[1].attributes.Whole, nil)
			check.equal(plain.children[2].attributes.Shard, nil)
		end)
		test.case("a model's far stand-in is carried by Roblox's own name, and a wrong name is not", function()
			local far = table.clone(MANIFEST)
			far.far = "StreamingMesh"
			local ids = { models = { rifle = "rbxassetid://1", rifle_glass = "rbxassetid://2" } }
			check.equal(Models.compile("rifle", far, ids).attributes.Far, "StreamingMesh")
			far.far = "Billboard"
			check.equal(Models.compile("rifle", far, ids).attributes.Far, nil)
			check.equal(Models.compile("rifle", MANIFEST, ids).attributes.Far, nil)
		end)
		test.case("a group's physics material is carried, and a group with none carries none", function()
			local phys = table.clone(MANIFEST)
			phys.groups = table.clone(MANIFEST.groups)
			phys.groups.main = table.clone(MANIFEST.groups.main)
			phys.groups.main.physics = { friction = 1.4, elasticity = 0.1 }
			local ids = { models = { rifle = "rbxassetid://1", rifle_glass = "rbxassetid://2" } }
			local model = Models.compile("rifle", phys, ids)
			check.equal(model.children[1].attributes.PhysFriction, 1.4)
			check.equal(model.children[1].attributes.PhysElasticity, 0.1)
			check.equal(model.children[1].attributes.PhysDensity, nil)
			check.equal(model.children[2].attributes.PhysFriction, nil)
		end)
		test.case("a module of a kit carries the cell it snaps by and the cells it takes", function()
			local wall = table.clone(MANIFEST)
			wall.module = { grid = { 4, 4, 0 }, cells = { 2, 1, 0 } }
			local ids = { models = { rifle = "rbxassetid://1", rifle_glass = "rbxassetid://2" } }
			local model = Models.compile("rifle", wall, ids)
			check.equal(model.attributes.ModuleGrid.Vector3[1], 4)
			check.equal(model.attributes.ModuleGrid.Vector3[3], 0)
			check.equal(model.attributes.ModuleCells.Vector3[1], 2)
			check.equal(Models.compile("rifle", MANIFEST, ids).attributes.ModuleGrid, nil)
		end)
		test.case("a model's own motion is carried as the table the game plays, one value a cycle", function()
			local moving = table.clone(MANIFEST)
			moving.cycles = {
				{
					name = "Open",
					fps = 24,
					keys = {},
					marks = {},
					play = {
						fps = 24,
						loop = false,
						length = 1,
						joints = { "Lid" },
						kinds = { "hinge" },
						times = { 0, 1 },
						values = { { 0 }, { 90 } },
						marks = { click = 0.5 },
					},
				},
				{ name = "Old", fps = 24, keys = {}, marks = {} }, -- (a manifest from before the table: left out)
			}
			local ids = { models = { rifle = "rbxassetid://1", rifle_glass = "rbxassetid://2" } }
			local model = Models.compile("rifle", moving, ids)
			local folder = model.children[#model.children]
			check.equal(folder.name, "Cycles")
			check.equal(#folder.children, 1)
			check.equal(folder.children[1].name, "Open")
			check.equal(folder.children[1].className, "StringValue")
			local serde = require("@lune/serde")
			local back = serde.decode("json", folder.children[1].properties.Value)
			check.equal(back.values[2][1], 90)
			check.equal(back.marks.click, 0.5)
			check.equal(back.joints[1], "Lid")
			local plain = Models.compile("rifle", MANIFEST, ids)
			check.equal(plain.children[#plain.children].name ~= "Cycles", true)
		end)
		test.case("a cycle too long for a model file's value stops the compile by its name", function()
			local long = table.clone(MANIFEST)
			local times, values = {}, {}
			for i = 1, 30000 do
				times[i] = i / 24
				values[i] = { i * 0.123456 }
			end
			long.cycles = {
				{
					name = "Forever",
					play = { joints = { "Lid" }, kinds = { "hinge" }, times = times, values = values },
				},
			}
			local ok, err = pcall(Models.compile, "rifle", long, {})
			check.equal(ok, false)
			check.equal(string.find(tostring(err), 'cycle "Forever"', 1, true) ~= nil, true)
		end)
		test.case("each mesh carries the collision shape and level of detail the build chose", function()
			local set = table.clone(MANIFEST)
			set.groups = table.clone(MANIFEST.groups)
			set.groups.main = table.clone(MANIFEST.groups.main)
			set.groups.main.collision_fidelity = "Hull"
			set.groups.main.render_fidelity = "Precise"
			local ids = { models = { rifle = "rbxassetid://1", rifle_glass = "rbxassetid://2" } }
			local model = Models.compile("rifle", set, ids)
			check.equal(model.children[1].attributes.CollisionFidelity, "Hull")
			check.equal(model.children[1].attributes.RenderFidelity, "Precise")
			check.equal(model.children[2].attributes.CollisionFidelity, nil) -- (a group with none: Roblox's default)
			local plain = Models.compile("rifle", MANIFEST, ids)
			check.equal(plain.children[1].attributes.CollisionFidelity, nil)
		end)
		test.case("a setting Roblox does not have stops the compile by name", function()
			local bad = table.clone(MANIFEST)
			bad.groups = table.clone(MANIFEST.groups)
			bad.groups.main = table.clone(MANIFEST.groups.main)
			bad.groups.main.collision_fidelity = "Sphere"
			local ok, err = pcall(Models.compile, "rifle", bad, {})
			check.equal(ok, false)
			check.equal(string.find(tostring(err), "rifle/main collision_fidelity Sphere", 1, true) ~= nil, true)
		end)
		test.case("files not uploaded yet are listed, the mesh id stays empty", function()
			local model, missing = Models.compile("rifle", MANIFEST, { textures = { rifle_color = "rbxassetid://3" } })
			check.equal(model.children[1].attributes.MeshId, "")
			check.is_true(table.find(missing, "rifle") ~= nil)
			check.is_true(table.find(missing, "rifle_normal") ~= nil)
		end)
		test.case("maps recorded under the older 'models' kind are still found", function()
			local model = Models.compile(
				"rifle",
				MANIFEST,
				{ models = { rifle = "rbxassetid://1", rifle_color = "rbxassetid://9" } }
			)
			check.equal(model.children[1].children[1].properties.ColorMap, "rbxassetid://9")
		end)
	end)
end
