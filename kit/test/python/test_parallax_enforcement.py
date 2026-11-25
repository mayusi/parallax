"""test_parallax_enforcement.py - the 16 exit criteria of PARALLAX_ENFORCEMENT_AND_ROUTING_SPEC §5.3 (the Python
side; kit/test/spec/enforcer.spec.luau proves the CLI kernel gate's half of 7, 8, 10, 13 and 15).

Every case runs on a temporary session file (PARALLAX_SESSION_FILE) and temporary PROMPT-X stores: the checkout's own
.verify/parallax_session.json and vault are never touched.
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit"))
sys.path.insert(0, os.path.join(ROOT, "kit", "scripts"))
sys.path.insert(0, os.path.join(ROOT, "kit", "mcp"))

import lane_fence  # noqa: E402
import parallax_guard as guard  # noqa: E402
from prompt import cases, cli, evolve, route, session  # noqa: E402
from prompt import compile as comp  # noqa: E402

ENV_KEYS = ("PARALLAX_SESSION_FILE", "PARALLAX_GAME", "KIT_GAME", "PARALLAX_ENFORCE", "KIT_ENFORCE", "PARALLAX_ROOT",
            "KIT_PROMPT_VAULT", "KIT_PROMPT_TRACES", "PARALLAX_EXEMPT", "PARALLAX_SESSION_ID")


def lune():
    return shutil.which("lune") or os.path.join(os.path.expanduser("~"), ".rokit", "bin", "lune.exe")


class Env(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._env = {k: os.environ.get(k) for k in ENV_KEYS}
        for k in ENV_KEYS:
            os.environ.pop(k, None)
        self.sfile = os.path.join(self.tmp, "parallax_session.json")
        os.environ["PARALLAX_SESSION_FILE"] = self.sfile
        os.environ["PARALLAX_GAME"] = "none"
        os.environ["KIT_PROMPT_VAULT"] = os.path.join(self.tmp, "vault")
        os.environ["KIT_PROMPT_TRACES"] = os.path.join(self.tmp, "traces.json")

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_hook(self, fn, event):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = fn(event)
        return code, out.getvalue(), err.getvalue()

    def stamp(self, raw="make a gothic sword", lane="3d", **over):
        p = comp.compile_packet(route.route_intent(raw, "none", lane), {}, "claude")
        sha = evolve.save_packet(p)  # (a real compiled packet: the session's prompt_sha must name one)
        s = session.stamp(p, os.path.join(self.tmp, "last.json"), sha, lane=lane)
        if over:
            s.update(over)
            session.write(s)
        return s


def edit(path):
    return {"tool_name": "Edit", "tool_input": {"file_path": path}, "session_id": None}


def bash(cmd):
    return {"tool_name": "Bash", "tool_input": {"command": cmd}}


class C01NonPipelineZeroInterference(Env):
    def test_readme_git_status_pytest_exit_0_silently_fast(self):
        guard.pre_tool(edit("README.md"))  # (warm the imports: a hook process pays them once)
        for ev in (edit("README.md"), edit(os.path.join(ROOT, "README.md")), bash("git status"),
                   bash("python -m pytest kit/test/python -q"), edit("LIMITATIONS_FIXES_V4.md"),
                   edit("board/journal/2026-11-21.md")):
            t0 = time.perf_counter()
            code, out, err = self.run_hook(guard.pre_tool, ev)
            ms = (time.perf_counter() - t0) * 1000
            self.assertEqual((code, out, err), (0, "", ""), ev)
            self.assertLess(ms, 15, f"{ev}: {ms:.1f} ms")


class C02BootstrapAllowlistNoDeadlock(Env):
    def test_bootstrap_and_read_only_commands_pass_with_no_session(self):
        self.assertFalse(os.path.exists(self.sfile))
        for cmd in ('lune run parallax prompt compile "make a gothic sword"', "lune run parallax start 3d",
                    "lune run parallax status", "cd foo && lune run parallax verify", "lune run kit case 3d sword",
                    "lune run parallax selftest --lane vfx", "lune run kit asset all", "lune run kit help --all",
                    'lune run kit asset sword --maintenance "rebuild after a kit fix"', "lune run kit vfx list"):
            code, _, err = self.run_hook(guard.pre_tool, bash(cmd))
            self.assertEqual(code, 0, f"{cmd}: {err}")


class C03UninitialisedPipelineWriteBlocked(Env):
    def test_build_script_writes_blocked_with_the_unlock_command(self):
        for p in ("assets/models/build_foo.py", "games\\SampleRegion\\assets\\models\\build_foo.py",
                  os.path.join(ROOT, "assets", "effects", "x.json")):
            code, _, err = self.run_hook(guard.pre_tool, edit(p))
            self.assertEqual(code, 2, p)
            self.assertIn('lune run parallax start', err)
            self.assertIn('--prompt', err)
        code, _, err = self.run_hook(guard.pre_tool, bash("lune run kit asset sword"))
        self.assertEqual(code, 2)
        self.assertIn("lune run parallax start 3d --prompt", err)
        code, _, err = self.run_hook(guard.pre_tool, bash("echo x > assets/worlds/Town.json"))
        self.assertEqual(code, 2)


class C04GeneratedAndKitLaneProtection(Env):
    def test_generated_always_blocked_kit_only_for_the_kit_lane(self):
        self.stamp()  # a fresh 3d session
        for p in ("src/ui/Hud.model.json", "src/models/Sword.model.json", "src/net/CombatNet.luau", "src/moves/Katana.luau"):
            self.assertEqual(self.run_hook(guard.pre_tool, edit(p))[0], 2, p)
        self.assertEqual(self.run_hook(guard.pre_tool, edit("kit/lib/cli.luau"))[0], 2)
        for lane in ("parallax", "kit"):
            self.stamp(raw="fix the kit's cli gate", lane=lane)
            self.assertEqual(self.run_hook(guard.pre_tool, edit("kit/lib/cli.luau"))[0], 0, lane)
            self.assertEqual(self.run_hook(guard.pre_tool, edit("src/ui/Hud.model.json"))[0], 2)


class C04bGamePerPath(Env):
    def test_a_root_session_while_another_game_is_active(self):
        # (found live 2026-11-21: a hook has no --game, so games/.active must not decide a kit or root-path edit)
        self.stamp(raw="fix the kit's cli gate", lane="kit")  # made with PARALLAX_GAME=none: game None
        os.environ["PARALLAX_GAME"] = "SomeOtherGame"  # (the checkout's active game is another one)
        self.assertEqual(self.run_hook(guard.pre_tool, edit("kit/lib/cli.luau"))[0], 0)
        self.assertEqual(self.run_hook(guard.pre_tool, edit("assets/models/build_foo.py"))[0], 0)  # (a root path)
        self.assertEqual(self.run_hook(guard.pre_tool, edit("games/SomeOtherGame/assets/models/build_foo.py"))[0], 2)
        self.assertEqual(self.run_hook(guard.pre_tool, bash("lune run kit asset foo --game none"))[0], 0)
        self.assertEqual(self.run_hook(guard.pre_tool, bash("lune run kit asset foo"))[0], 2)  # (the active game)


class R01ReviewFindings(Env):
    """the fresh review of c556af9c46 (2026-11-21): every hole it reproduced, closed"""

    def test_wrappers_do_not_hide_a_mutating_command(self):
        for cmd in ("env PARALLAX_ENFORCE=x lune run kit vfx foo", "timeout 600 lune run kit vfx foo",
                    "nohup lune run kit asset foo", "time lune run kit asset foo", "echo foo | xargs lune run kit asset",
                    "& lune run kit asset foo", "Start-Process lune -ArgumentList 'run kit asset foo'",
                    'pwsh -NoProfile -c "lune run kit asset foo"', 'bash -c "cd x && lune run kit asset foo"'):
            self.assertEqual(self.run_hook(guard.pre_tool, bash(cmd))[0], 2, cmd)

    def test_setting_the_gate_switches_in_a_shell_is_tampering(self):
        self.stamp()  # (a 3d session: not enough to change the gate's own switches)
        for cmd in ("PARALLAX_EXEMPT=1 lune run kit status", "export KIT_ENFORCE=off",
                    "$env:PARALLAX_EXEMPT = '1'; lune run kit status"):
            self.assertEqual(self.run_hook(guard.pre_tool, bash(cmd))[0], 2, cmd)

    def test_the_session_token_cannot_be_written_by_hand(self):
        self.assertEqual(self.run_hook(guard.pre_tool, edit(".verify/parallax_session.json"))[0], 2)
        self.assertEqual(self.run_hook(guard.pre_tool, bash("echo '{}' > .verify/parallax_session.json"))[0], 2)
        forged = {"schema": 1, "started_at": session.now_iso(), "ttl_seconds": 14400, "prompt_sha": "abcdef123456",
                  "lane": "kit", "branch": session.branch(), "game": None}
        session.write(forged)
        self.assertEqual(self.run_hook(guard.pre_tool, edit("kit/lib/cli.luau"))[0], 2)

    def test_quoted_text_and_heredocs_are_not_commands(self):
        for cmd in ('git commit -m "docs; lune run kit ui foo now works"',
                    "python - <<'EOF'\nprint('lune run kit vfx foo was slow')\nEOF",
                    "cat > /tmp/note.txt <<EOF\nlune run kit asset foo\nEOF"):
            self.assertEqual(self.run_hook(guard.pre_tool, bash(cmd))[0], 0, cmd)

    def test_every_path_form_is_seen(self):
        root = guard.repo_root().replace("\\", "/")
        gitbash = "/" + root[0].lower() + root[2:] + "/assets/models/x.py"
        for p in (gitbash, "Assets/Models/x.py", "\\\\?\\" + root.replace("/", "\\") + "\\assets\\models\\x.py",
                  "games/SampleRegion/../../assets/models/x.py"):
            self.assertEqual(self.run_hook(guard.pre_tool, edit(p))[0], 2, p)
        for cmd in ("touch assets/models/x.py", "curl -o assets/sounds/x.ogg https://example.invalid/x",
                    "git checkout -- assets/effects/x.json", "cd games/SampleRegion && echo x > assets/models/y.py"):
            self.assertEqual(self.run_hook(guard.pre_tool, bash(cmd))[0], 2, cmd)

    def test_the_security_reviews_path_and_parser_forms(self):
        # (the automated security review of 1fa81d6b98: case, trailing dots, streams, 8.3 names, heredocs fed to a
        # shell, eval, a moved-away source)
        for p in ("ASSETS/models/x.py", "assets./models/x.py", "assets/models/x.json::$DATA", "ASSETS~1/models/x.py",
                  ".verify/parallax_session.json."):
            self.assertEqual(self.run_hook(guard.pre_tool, edit(p))[0], 2, p)
        for cmd in ("bash <<'EOF'\nlune run kit asset foo\nEOF", "eval lune run kit asset foo",
                    "mv assets/models/x.py /tmp/", "LUNE run KIT asset foo".replace("LUNE", "lune")):
            self.assertEqual(self.run_hook(guard.pre_tool, bash(cmd))[0], 2, cmd)
        self.assertEqual(self.run_hook(guard.pre_tool, bash("cat > /tmp/n.txt <<EOF\nlune run kit asset foo\nEOF"))[0], 0)
        # (its second pass: a heredoc any shell / sudo / unknown program receives is parsed; eval re-splits its words;
        # a repo-local script run is pipeline work; outside scripts and plain commands are not)
        for cmd in ("sudo bash <<'EOF'\nlune run kit asset foo\nEOF", "env X=1 sh <<EOF\nlune run kit asset foo\nEOF",
                    "eval 'lune run kit asset foo'", "sh _scratch/x.sh", "source ./x.sh", "./build.sh"):
            self.assertEqual(self.run_hook(guard.pre_tool, bash(cmd))[0], 2, cmd)
        for cmd in ("sh /tmp/outside.sh", "python - <<'EOF'\nprint('lune run kit asset foo')\nEOF", "ls kit/"):
            self.assertEqual(self.run_hook(guard.pre_tool, bash(cmd))[0], 0, cmd)

    def test_staging_a_rebuilt_generated_file_is_not_a_hand_edit(self):
        # (found live 2026-11-21: the guard refused `git add src/models/x.model.json` after kit upload rebuilt it)
        self.assertEqual(self.run_hook(guard.pre_tool, bash("git add src/models/sword.model.json"))[0], 2)  # no session
        self.stamp()
        self.assertEqual(self.run_hook(guard.pre_tool, bash("git add src/models/sword.model.json"))[0], 0)
        self.assertEqual(self.run_hook(guard.pre_tool, edit("src/models/sword.model.json"))[0], 2)  # (an edit: never)
        self.assertEqual(self.run_hook(guard.pre_tool, bash("echo x > src/models/sword.model.json"))[0], 2)
        # (only git add's own pathspecs: a redirect riding on it, or git rm, stays the hard block)
        self.assertEqual(self.run_hook(guard.pre_tool, bash("git add src/models/a.model.json > src/ui/Hud.model.json"))[0], 2)
        self.assertEqual(self.run_hook(guard.pre_tool, bash("git rm src/models/sword.model.json"))[0], 2)

    def test_nesting_past_the_cap_is_a_block_no_session_unlocks(self):
        self.stamp(raw="fix the kit", lane="kit")  # (even the kit lane)
        self.assertEqual(self.run_hook(guard.pre_tool, bash("eval " * 12 + "lune run kit status"))[0], 2)
        self.assertEqual(self.run_hook(guard.pre_tool, bash("eval eval lune run kit status"))[0], 0)

    def test_a_session_unlocks_its_own_lane_only(self):
        self.stamp(raw="a fire slash effect", lane="vfx")
        self.assertEqual(self.run_hook(guard.pre_tool, edit("assets/effects/slash.json"))[0], 0)
        code, _, err = self.run_hook(guard.pre_tool, edit("assets/models/build_foo.py"))
        self.assertEqual(code, 2)
        self.assertIn("lune run parallax start 3d", err)

    def test_the_unlock_names_the_game_of_the_work(self):
        code, _, err = self.run_hook(guard.pre_tool, edit("games/SampleRegion/assets/worlds/x.json"))
        self.assertEqual(code, 2)
        self.assertIn("--game SampleRegion", err)
        code, _, err = self.run_hook(guard.pre_tool, edit("assets/worlds/x.json"))
        self.assertIn("--game none", err)

    def test_stop_reminds_for_a_root_session_while_another_game_is_active(self):
        self.stamp()  # (game None)
        os.environ["PARALLAX_GAME"] = "SomeOtherGame"
        rel = "assets/models/build_parallax_spec_probe.py"
        guard.post_tool(edit(os.path.join(ROOT, rel)))
        self.assertIn(rel, session.read()["touched_pipeline_files"])
        code, out, _ = self.run_hook(guard.stop, {})
        self.assertEqual(json.loads(out)["decision"], "block")

    def test_a_docs_only_commit_never_runs_the_harness_check(self):
        called = []
        real = guard.harness_check
        guard.harness_check = lambda root: (called.append(root) or (False, "stale"))
        try:
            with redirect_stdout(io.StringIO()):
                self.assertEqual(guard.pre_commit([], root=self.tmp, files=["README.md", "board/x.md"]), 0)
                self.assertEqual(called, [])
                self.assertEqual(guard.pre_commit([], root=self.tmp, files=["kit/skills/parallax-vfx/SKILL.md"]), 1)
        finally:
            guard.harness_check = real

    def test_the_mcp_gate_reads_the_calls_game(self):
        import server  # noqa: PLC0415

        self.stamp(raw="a fire slash effect", lane="vfx")  # (game None)
        os.environ["PARALLAX_GAME"] = "SomeOtherGame"
        self.assertIsNone(server.gate(["vfx", "slash", "--game", "none"]))
        self.assertIsNotNone(server.gate(["asset", "sword", "--game", "none"]))  # (another lane)

    def test_signal_b_is_a_real_check(self):
        code, _, err = self.run_hook(guard.pre_tool, {"tool_name": "mcp__parallax__parallax", "tool_input": {}})
        self.assertEqual(code, 2)
        self.stamp()
        os.environ["PARALLAX_GAME"] = "none"
        self.assertEqual(self.run_hook(guard.pre_tool, {"tool_name": "mcp__parallax__parallax", "tool_input": {}})[0], 0)


class C05SessionUnlocksPipelineWrite(Env):
    def test_compile_writes_the_session_with_the_case_and_unlocks(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = cli.main(["compile", "make a gothic sword", "--lane", "3d", "--out", os.path.join(self.tmp, "p.json")])
        self.assertEqual(code, 0, out.getvalue()[-400:])
        s = json.load(open(self.sfile, encoding="utf-8"))
        self.assertEqual(s["lane"], "3d")
        self.assertTrue(s["prompt_sha"])
        self.assertIn("3d:hybrid_hero", [c["case_id"] for c in s["case_contracts"]])
        self.assertEqual(session.problems(s), [])
        self.assertEqual(self.run_hook(guard.pre_tool, edit("assets/models/build_foo.py"))[0], 0)
        self.assertEqual(self.run_hook(guard.pre_tool, bash("lune run kit asset foo"))[0], 0)


class C06CaseAntiPatternsOnEditAndCommit(Env):
    def write(self, rel, text):
        root = os.path.join(self.tmp, "repo")
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)
        return root, p

    def test_post_tool_flags_and_pre_commit_refuses(self):
        rows = [("assets/effects/burst.json", '{"layers": [{"kind": "mesh", "erode": 0.5}]}'),
                ("src/shared/Moves.luau", "local t0 = os.clock()\n"),
                ("src/server/Combat.server.luau", "remote.OnServerEvent:Connect(function(p, x) end)\n")]
        for rel, text in rows:
            root, p = self.write(rel, text)
            os.environ["PARALLAX_ROOT"] = root
            code, _, err = self.run_hook(guard.post_tool, edit(p))
            self.assertEqual(code, 2, f"{rel}: {err}")
            self.assertIn("[parallax] BLOCK", err)
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(guard.pre_commit([], root=root, files=[rel], check_harness=False), 1, rel)
        root, p = self.write("src/server/Safe.server.luau", "Guard.check(x)\nremote.OnServerEvent:Connect(f)\n")
        os.environ["PARALLAX_ROOT"] = root
        self.assertEqual(self.run_hook(guard.post_tool, edit(p))[0], 0)


class C08EscapeHatchesNeverStall(Env):
    def test_governance_maintenance_and_off(self):
        for cmd in ("lune run kit verify --profile core", "lune run kit prove", "lune run kit doctor",
                    'lune run kit vfx starblade --maintenance "re-render after a player fix"'):
            self.assertEqual(self.run_hook(guard.pre_tool, bash(cmd))[0], 0, cmd)
        os.environ["PARALLAX_ENFORCE"] = "audit"
        code, _, err = self.run_hook(guard.pre_tool, edit("assets/models/build_foo.py"))
        self.assertEqual(code, 0)
        self.assertIn("audit", err)
        os.environ["PARALLAX_ENFORCE"] = "off"
        real_stdin = sys.stdin
        try:  # (the hook process itself, off: it reads the event and lets the blocked write through)
            sys.stdin = io.StringIO(json.dumps(edit("assets/models/build_foo.py")))
            self.assertEqual(guard.main(["--hook", "pre-tool"]), 0)
        finally:
            sys.stdin = real_stdin
        os.environ["PARALLAX_ENFORCE"] = "enforce"
        self.assertEqual(self.run_hook(guard.pre_tool, edit("assets/models/build_foo.py"))[0], 2)

    def test_off_is_ignored_by_pre_commit_without_maintenance(self):
        root = os.path.join(self.tmp, "repo")
        os.makedirs(os.path.join(root, "assets", "effects"))
        with open(os.path.join(root, "assets", "effects", "x.json"), "w", encoding="utf-8") as fh:
            fh.write('{"erode": 1}')
        os.environ["PARALLAX_ENFORCE"] = "off"
        with redirect_stdout(io.StringIO()):
            self.assertEqual(guard.pre_commit([], root=root, files=["assets/effects/x.json"], check_harness=False), 1)
            self.assertEqual(guard.pre_commit(["--maintenance", "a kit fix"], root=root, files=["assets/effects/x.json"],
                                              check_harness=False), 0)


class C09LaneFenceEnforcedCodeQaTogether(unittest.TestCase):
    def test_enforce_mode_cross_and_together(self):
        lanes = lane_fence.load_lanes(os.path.join(ROOT, "kit", "knowledge", "lanes.json"))
        self.assertEqual(lanes["mode"], "enforce")
        self.assertIn(["code", "qa"], lanes["together"])
        self.assertFalse(lane_fence.check(["assets/models/a.py", "assets/effects/b.json"], "feat: two lanes", lanes)[0])
        self.assertTrue(lane_fence.check(["assets/models/a.py", "assets/effects/b.json"], "feat: cross on purpose", lanes)[0])
        self.assertTrue(lane_fence.check(["src/server/X.server.luau", "tests/playtest/x.luau"], "feat: a system", lanes)[0])
        for prefix in ("kit/world/", "src/materials/"):
            self.assertIn(prefix, lanes["lanes"]["world"])
        for lane in ("code", "qa", "parallax"):
            self.assertIn(lane, lanes["lanes"])


class C10HarnessDriftFailsPreCommit(Env):
    def test_a_stale_harness_refuses_the_commit(self):
        real = guard.harness_check
        guard.harness_check = lambda root: (False, "  ~ .claude/skills/parallax-sharpen/SKILL.md")
        try:
            with redirect_stdout(io.StringIO()) as out:
                self.assertEqual(guard.pre_commit([], root=self.tmp, files=["kit/skills/parallax-sharpen/SKILL.md"],
                                                  check_harness=True), 1)
            self.assertIn("parallax harness", out.getvalue())
        finally:
            guard.harness_check = real
        guard.harness_check = lambda root: (True, "")
        try:
            with redirect_stdout(io.StringIO()):
                self.assertEqual(guard.pre_commit([], root=self.tmp, files=["kit/skills/parallax-sharpen/SKILL.md"],
                                                  check_harness=True), 0)
        finally:
            guard.harness_check = real

    def test_the_real_harness_check_runs_and_is_clean(self):
        ok, text = guard.harness_check(ROOT)  # (no stand-in: the real `parallax harness --check`)
        self.assertTrue(ok, text[-600:])
        self.assertIn("in step", text)


class C11McpGate(Env):
    def test_mutating_call_without_a_session_is_an_error_with_the_next_call(self):
        import server  # noqa: PLC0415

        calls = []
        real = server.run_kit
        server.run_kit = lambda args: (calls.append(args) or "ran", False)
        try:
            text, is_error = server.call_tool("parallax", {"args": ["asset", "sword"]})
            self.assertTrue(is_error)
            self.assertIn("parallax_start", text)
            self.assertIn('"dept": "3d"', text)
            self.assertEqual(calls, [])
            # bootstrap / read-only calls go through
            self.assertFalse(server.call_tool("parallax", {"args": ["status"]})[1])
            self.assertFalse(server.call_tool("kit_status", {})[1])  # (the old name still answers)
            # parallax_prompt and parallax_start(prompt=...) are the unlock calls
            server.call_tool("parallax_prompt", {"prompt": "make a gothic sword", "lane": "3d"})
            server.call_tool("parallax_start", {"dept": "3d", "prompt": "make a gothic sword"})
            self.assertEqual(calls[-2], ["prompt", "compile", "make a gothic sword", "--lane", "3d"])
            self.assertEqual(calls[-1], ["start", "3d", "--prompt", "make a gothic sword"])
            self.stamp()
            self.assertEqual(server.call_tool("parallax", {"args": ["asset", "sword"]}), ("ran", False))
        finally:
            server.run_kit = real

    def test_the_server_is_parallax_4(self):
        import server  # noqa: PLC0415

        names = [t["name"] for t in server.TOOLS]
        for n in ("parallax_start", "parallax_prompt", "parallax_case", "parallax_skill", "parallax_status",
                  "parallax_verify", "parallax_help", "parallax"):
            self.assertIn(n, names)
        with open(os.path.join(ROOT, "kit", "VERSION"), encoding="utf-8") as f:
            self.assertEqual(server.VERSION, f.read().strip())  # (one release version everywhere)


class C12ScopedStopHookNoLoop(Env):
    def test_silent_unless_dirty_once(self):
        self.assertEqual(self.run_hook(guard.stop, {"stop_hook_active": True}), (0, "", ""))
        self.assertEqual(self.run_hook(guard.stop, {}), (0, "", ""))  # (no session)
        self.stamp()
        self.assertEqual(self.run_hook(guard.stop, {}), (0, "", ""))  # (nothing touched)
        self.stamp(touched_pipeline_files=["assets/models/build_foo.py"], session_id="A")
        self.assertEqual(self.run_hook(guard.stop, {"session_id": "B"}), (0, "", ""))  # (another session's)
        self.assertEqual(self.run_hook(guard.stop, {"stop_hook_active": True, "session_id": "A"}), (0, "", ""))
        code, out, _ = self.run_hook(guard.stop, {"session_id": "A"})
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["decision"], "block")
        self.assertEqual(self.run_hook(guard.stop, {"session_id": "A"}), (0, "", ""))  # (once only)
        s = session.read()
        s["reminded_at"], s["verify_passed_at"] = None, session.now_iso()
        session.write(s)
        self.assertEqual(self.run_hook(guard.stop, {"session_id": "A"}), (0, "", ""))  # (proven: quiet)

    def test_post_tool_tracks_the_files_it_touched(self):
        self.stamp()
        rel = "assets/models/build_parallax_spec_probe.py"
        p = os.path.join(ROOT, rel)
        self.assertFalse(os.path.exists(p))
        guard.post_tool(edit(p))  # (no file on disk: tracked, nothing to scan)
        self.assertIn(rel, session.read()["touched_pipeline_files"])


class C13BrandShims(Env):
    def test_bench_identical_under_both_names(self):
        outs = []
        for name in ("parallax", "kit"):
            p = subprocess.run([lune(), "run", name, "prompt", "bench", "--game", "none"], cwd=ROOT, capture_output=True,
                               text=True, encoding="utf-8", errors="replace", timeout=600,
                               env=dict(os.environ, PARALLAX_EXEMPT="1"))
            self.assertEqual(p.returncode, 0, p.stdout[-400:] + p.stderr[-400:])
            outs.append([ln for ln in p.stdout.splitlines() if ln.startswith(("summary:", "next_action:"))])
        self.assertEqual(outs[0], outs[1])
        self.assertTrue(outs[0])

    def test_parallax_env_first(self):
        os.environ["KIT_GAME"] = "SampleGame"
        os.environ["PARALLAX_GAME"] = "none"
        self.assertIsNone(session.active_game())
        os.environ["PARALLAX_ENFORCE"], os.environ["KIT_ENFORCE"] = "audit", "off"
        self.assertEqual(guard.mode(), "audit")


class C14CaseContractCoverage(unittest.TestCase):
    def test_40_cases_validate_and_route_their_examples(self):
        n, problems = cases.validate_all()
        self.assertEqual(problems, [])
        self.assertEqual(n, 40)
        for lane in cases.CASE_LANES:
            reg = cases.registry(lane)
            self.assertTrue(reg["cases"], lane)
            for c in reg["cases"]:
                self.assertTrue(c["examples"], c["case_id"])
                self.assertIn("Full-capability", c["capability_policy"])
            self.assertLessEqual(len(cases.render_menu(lane)), cases.MENU_LINES)
        self.assertEqual(cases.match("3d", "make a gothic sword")[0]["case_id"], "3d:hybrid_hero")


class C15LivingToolPlanFeedsEvolve(Env):
    def test_ingest_plan_and_winning_tools(self):
        root = os.path.join(self.tmp, "repo")
        os.makedirs(os.path.join(root, "assets", "plans"))
        plan = {"schema": 1, "piece": "h9_sword", "lane": "3d", "case_id": "3d:hybrid_hero", "revision": 2,
                "prompt_sha": "a1b2", "part_or_beat_tools": [{"target": "blade", "tools": ["a.cad", "hybrid_fabricate"]}],
                "considered_and_skipped": [], "escalations": [{"target": "pommel", "tools": ["vision_plate", "gen_1024"]}]}
        with open(os.path.join(root, "assets", "plans", "h9_sword.plan.json"), "w", encoding="utf-8") as fh:
            json.dump(plan, fh)
        rec = evolve.ingest_plan("h9_sword", 8.5, root=root)
        self.assertEqual(rec["case_id"], "3d:hybrid_hero")
        self.assertEqual(rec["tools"], ["a.cad", "hybrid_fabricate", "vision_plate", "gen_1024"])
        wins = dict(evolve.winning_tools("3d:hybrid_hero"))
        self.assertEqual(wins.get("gen_1024"), 1)
        self.assertIsNone(evolve.ingest_plan("no_plan_piece", 9, root=root))


class C16PromptXCarriesCasesAndMenus(Env):
    def test_routed_and_compiled(self):
        r = route.route_intent("make a gothic sword with a carved lion pommel", "none", "3d")
        self.assertIn("3d:hybrid_hero", [c["case_id"] for c in r["case_contracts"]])
        self.assertTrue(r["capability_menu"])
        for model in ("claude", "codex", "gemini", "local"):
            p = comp.compile_packet(r, {}, model)
            self.assertIn("3d:hybrid_hero", [c["case_id"] for c in p["case_contracts"]])
            self.assertLessEqual(p["token_count"], comp.models.profile(model)["budget"])
        self.assertIn("case 3d:hybrid_hero", comp.compile_packet(r, {}, "claude")["orchestrator_prompt"])

    def test_parallax_case_prints_at_most_25_lines(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(cli.main(["case", "vfx", "a fire katana slash"]), 0)
        res = json.loads(out.getvalue().strip().splitlines()[-1])
        self.assertLessEqual(len(res["lines"]), 25)
        self.assertTrue(res["contract"]["case_id"].startswith("vfx:"))


if __name__ == "__main__":
    unittest.main()
