"""test_mcp_server.py — the kit's MCP server (kit/mcp/server.py): kit_start is the FIRST tool, its dept enum is exactly
the nine lanes, and the server advertises one start-<lane> prompt per lane for clients that show prompts. The rules
travel with the server (initialize's instructions = the enforcement head + kit/harness/AGENTS.parallax.md, so no client
needs an instruction file), and a lane's recipe and the command list arrive WHOLE - a long skill page trimmed to its
last lines would lose the stages it opens with.

Runs the server as a subprocess from the project root: it speaks JSON-RPC 2.0 over stdin/stdout, one message per line.
All requests go through ONE process; the tests read its responses by id. kit_start is only called with a bad dept here:
a real lane would run the whole kit command (slow).
"""
import json
import os
import subprocess
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
SERVER = os.path.join(ROOT, "kit", "mcp", "server.py")
RULES = os.path.join(ROOT, "kit", "harness", "AGENTS.parallax.md")
sys.path.insert(0, os.path.join(ROOT, "kit"))
sys.path.insert(0, os.path.join(ROOT, "kit", "scripts"))
sys.path.insert(0, os.path.join(ROOT, "kit", "mcp"))
LANES = ["3d", "vfx", "ui", "anim", "world", "sfx", "code", "qa", "kit"]

REQUESTS = [
    {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    {"jsonrpc": "2.0", "id": 3, "method": "prompts/list"},
    {"jsonrpc": "2.0", "id": 4, "method": "prompts/get", "params": {"name": "start-ui"}},
    {"jsonrpc": "2.0", "id": 5, "method": "prompts/get", "params": {"name": "start-nope"}},
    {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "kit_start", "arguments": {"dept": "nope"}}},
]


def run_server():
    """Send every request to one server process; return {id: response}."""
    stdin = "".join(json.dumps(req) + "\n" for req in REQUESTS)
    proc = subprocess.run([sys.executable, "-I", SERVER], input=stdin, capture_output=True, text=True, cwd=ROOT)
    if proc.returncode != 0:
        raise AssertionError(f"server exited {proc.returncode}: {proc.stderr[-800:]}")
    responses = {}
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line:
            response = json.loads(line)
            responses[response["id"]] = response
    return responses


class TestMcpServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.responses = run_server()

    def test_initialize_advertises_tools_and_prompts(self):
        capabilities = self.responses[1]["result"]["capabilities"]
        self.assertIn("tools", capabilities)
        self.assertIn("prompts", capabilities)

    def test_tools_list_puts_kit_start_first_with_the_nine_lanes(self):
        tools = self.responses[2]["result"]["tools"]
        # (PARALLAX spec §5.1 step 6: the server is "parallax"; kit_start still answers - the bad-dept call uses it)
        self.assertEqual(tools[0]["name"], "parallax_start")
        dept = tools[0]["inputSchema"]["properties"]["dept"]
        self.assertEqual(dept["enum"], LANES)
        self.assertEqual(len(dept["enum"]), 9)

    def test_prompts_list_has_one_start_prompt_per_lane(self):
        prompts = self.responses[3]["result"]["prompts"]
        self.assertEqual([prompt["name"] for prompt in prompts], [f"start-{lane}" for lane in LANES])
        self.assertEqual(len(prompts), 9)

    def test_prompts_get_returns_a_ui_user_message_and_rejects_unknown(self):
        result = self.responses[4]["result"]
        messages = result["messages"]
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["role"], "user")
        text = messages[0]["content"]["text"]
        self.assertIn("parallax_start", text)
        self.assertIn('"ui"', text)
        self.assertEqual(self.responses[5]["error"]["code"], -32602)

    def test_kit_start_rejects_an_unknown_dept(self):
        result = self.responses[6]["result"]
        self.assertTrue(result["isError"])
        text = result["content"][0]["text"]
        self.assertTrue(text.startswith("dept must be one of"), text)

    def test_initialize_sends_the_rules_as_instructions(self):
        with open(RULES, encoding="utf-8") as fh:
            rules = fh.read().strip()
        text = self.responses[1]["result"]["instructions"]
        self.assertTrue(text.startswith("Parallax is enforced"), text[:120])
        self.assertIn("parallax_start", text)
        self.assertIn(rules, text)


class TestWholeOutputWhereItMatters(unittest.TestCase):
    """in-process: run_kit is stood in for, so nothing runs the kit"""

    @classmethod
    def setUpClass(cls):
        import server  # noqa: PLC0415

        cls.server = server

    def test_skill_and_help_are_never_trimmed_the_rest_is(self):
        server, calls = self.server, []

        def fake(args, max_lines=server.MAX_LINES):
            calls.append((args, max_lines))
            return "ok", False

        with mock.patch.object(server, "run_kit", side_effect=fake):
            server.call_tool("parallax_skill", {"dept": "anim"})
            server.call_tool("parallax_help", {})
            server.call_tool("parallax_status", {})
        self.assertEqual(calls[0], (["skill", "anim"], None))
        self.assertEqual(calls[1], (["help"], None))
        self.assertEqual(calls[2][1], server.MAX_LINES)

    def test_run_kit_trims_only_when_asked(self):
        server = self.server
        lines = "\n".join(f"line {i}" for i in range(server.MAX_LINES + 140))
        done = subprocess.CompletedProcess(args=[], returncode=0, stdout=lines, stderr="")
        with mock.patch.object(server.subprocess, "run", return_value=done):
            whole, error = server.run_kit(["skill", "anim"], max_lines=None)
            trimmed, _ = server.run_kit(["status"])
        self.assertFalse(error)
        self.assertTrue(whole.startswith("line 0\n"))
        self.assertIn(f"line {server.MAX_LINES + 139}", whole)
        self.assertTrue(trimmed.startswith("... (140 earlier lines trimmed"), trimmed[:80])
        self.assertNotIn("line 0\n", trimmed)


if __name__ == "__main__":
    unittest.main()
