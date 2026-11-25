"""kit optimize splits the tier's triangle budget between a master's mesh groups (rbx_optimize.budgets): every group
keeps a floor (a trigger keeps its shape), the rest goes by size, the total is respected, and no group ever gets
more than the master had or Roblox's 20k a mesh."""

import ast
import os
import types
import unittest

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "blender", "rbx_optimize.py")
_tree = ast.parse(open(SRC, encoding="utf-8").read())
_nodes = [n for n in _tree.body if (isinstance(n, ast.FunctionDef) and n.name == "budgets")
          or (isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "ROBLOX_MESH_CAP" for t in n.targets))]
_ns = {}
# (rbx_optimize imports bpy: lift the pure function and its constant out — run them as a function body in _ns)
types.FunctionType(compile(ast.Module(_nodes, []), "optimize", "exec"), _ns)()
budgets = _ns["budgets"]

GJ = {"main": 66004, "trigger": 484, "leg": 1288, "top": 12846, "shell": 7232}  # the Gjallarhorn master


class TestBudgets(unittest.TestCase):
    def test_the_total_is_respected(self):
        out = budgets(GJ, 13050)
        self.assertLessEqual(sum(out.values()), 13050)
        self.assertGreater(sum(out.values()), 13050 * 0.97)  # (and spent: a budget left on the table is detail lost)

    def test_small_groups_keep_their_floor_big_ones_share_by_size(self):
        out = budgets(GJ, 13050)
        self.assertGreaterEqual(out["trigger"], 400)
        self.assertGreaterEqual(out["leg"], 400)
        self.assertGreater(out["main"], out["top"])
        self.assertGreater(out["top"], out["shell"])

    def test_never_more_than_the_master_had_nor_the_mesh_cap(self):
        out = budgets({"a": 300, "b": 90000}, 60000)
        self.assertEqual(out["a"], 300)  # a group already under its share keeps exactly what it had
        self.assertLessEqual(out["b"], 20000)  # Roblox's cap per mesh

    def test_a_budget_above_the_master_keeps_every_group_but_the_mesh_cap_still_holds(self):
        out = budgets(GJ, 200000)
        self.assertEqual({g: n for g, n in out.items() if g != "main"}, {g: n for g, n in GJ.items() if g != "main"})
        self.assertEqual(out["main"], 20000)  # 66k in one mesh is not a Roblox mesh, however big the budget


if __name__ == "__main__":
    unittest.main()
