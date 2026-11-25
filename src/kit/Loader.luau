--!strict
-- Loader (ReplicatedStorage.kit.Loader) — the game SKELETON's one entry point: every ModuleScript in a folder is a
-- service (server) or a controller (client) with an optional lifecycle:
--   return { deps = { "DataService" }, init = function(self, services) end, start = function(self, services) end }
--   Loader.run(ServerScriptService.MyGameServices)   -- init in dependency order, then every start (in its own thread)
-- Errors name the module ("[Loader] CombatService.init: ..."): one broken service never hides which one it was.
-- Loader.order (pure, kit/test/spec/loader.spec.luau): dependency order, unknown deps and cycles named.
local Loader = {}

export type Module = { name: string, deps: { string } }

-- order modules so every dependency comes first; errors name the missing dependency or the whole cycle
function Loader.order(mods: { Module }): ({ string }?, string?)
	local byName: { [string]: Module } = {}
	for _, m in mods do
		byName[m.name] = m
	end
	for _, m in mods do
		for _, d in m.deps do
			if not byName[d] then
				return nil, `{m.name} depends on "{d}", which is not in the folder`
			end
		end
	end
	local out, state = {}, {} :: { [string]: string }
	local stack: { string } = {}
	local function visit(name: string): string?
		if state[name] == "done" then
			return nil
		end
		if state[name] == "visiting" then
			local i = table.find(stack, name) or 1
			local cycle = table.concat({ table.unpack(stack, i) }, " -> ") .. " -> " .. name
			return `dependency cycle: {cycle}`
		end
		state[name] = "visiting"
		table.insert(stack, name)
		local deps = table.clone(byName[name].deps)
		table.sort(deps)
		for _, d in deps do
			local err = visit(d)
			if err then
				return err
			end
		end
		table.remove(stack)
		state[name] = "done"
		table.insert(out, name)
		return nil
	end
	local names = {}
	for _, m in mods do
		table.insert(names, m.name)
	end
	table.sort(names) -- deterministic: the same folder always starts in the same order
	for _, n in names do
		local err = visit(n)
		if err then
			return nil, err
		end
	end
	return out, nil
end

-- require every ModuleScript in `container`, init them in order, then start them; returns the modules by name
function Loader.run(container: Instance): { [string]: any }
	local mods: { [string]: any } = {}
	local list: { Module } = {}
	for _, child in container:GetChildren() do
		if child:IsA("ModuleScript") then
			local ok, mod = pcall(require, child)
			if not ok then
				error(`[Loader] {child.Name} failed to load: {mod}`, 0)
			end
			mods[child.Name] = mod
			local deps = if type(mod) == "table" and type(mod.deps) == "table" then mod.deps else {}
			table.insert(list, { name = child.Name, deps = deps })
		end
	end
	local order, err = Loader.order(list)
	if not order then
		error(`[Loader] {container:GetFullName()}: {err}`, 0)
	end
	for _, name in order do
		local m = mods[name]
		if type(m) == "table" and type(m.init) == "function" then
			local ok, e = pcall(m.init, m, mods)
			if not ok then
				error(`[Loader] {name}.init: {e}`, 0)
			end
		end
	end
	for _, name in order do
		local m = mods[name]
		if type(m) == "table" and type(m.start) == "function" then
			task.spawn(function()
				local ok, e = pcall(m.start, m, mods)
				if not ok then
					warn(`[Loader] {name}.start: {e}`)
				end
			end)
		end
	end
	return mods
end

return Loader
