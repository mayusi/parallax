"""session.py - the PARALLAX SESSION TOKEN (.verify/parallax_session.json, PARALLAX_ENFORCEMENT_AND_ROUTING_SPEC §2.2
Signal D): written by `parallax prompt compile` and `parallax start <lane> --prompt "..."`, read by the hooks
(kit/scripts/parallax_guard.py), the CLI gate (kit/lib/enforcer.luau reads the same file) and the MCP server.

A session is FRESH while: it parses, it is younger than its ttl_seconds (4 h), its branch is the checkout's branch,
its game is the active game, and - when both sides name one - its session_id is the harness's. Standard library only.
"""

import datetime
import hashlib
import json
import os
import re
import subprocess

SCHEMA = 1
TTL = 4 * 3600
REL = os.path.join(".verify", "parallax_session.json")
KIT_LANES = ("parallax", "kit")  # the lanes that may edit kit/ and src/kit/


def env(name, default=None):
    """PARALLAX_<name> first, then the old KIT_<name> (zero-breakage brand shim)"""
    for k in (f"PARALLAX_{name}", f"KIT_{name}"):
        v = os.environ.get(k)
        if v not in (None, ""):
            return v
    return default


def root():
    return env("ROOT") or os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))


def path(base=None):
    """the token's file: PARALLAX_SESSION_FILE (tests, a second checkout) else <root>/.verify/parallax_session.json"""
    return env("SESSION_FILE") or os.path.join(base or root(), REL)


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(text):
    try:
        return datetime.datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
    except (TypeError, ValueError):
        return None


def branch(base=None):
    """the checkout's branch, read from .git/HEAD (no git process on the hook's fast path)"""
    b = base or root()
    head = os.path.join(b, ".git", "HEAD")
    try:
        if os.path.isfile(os.path.join(b, ".git")):  # a worktree: .git is a file naming the real git dir
            with open(os.path.join(b, ".git"), encoding="utf-8") as fh:
                gd = fh.read().split("gitdir:", 1)[1].strip()
            head = os.path.join(gd if os.path.isabs(gd) else os.path.join(b, gd), "HEAD")
        with open(head, encoding="utf-8") as fh:
            ref = fh.read().strip()
    except (OSError, IndexError):
        return None
    return ref.rsplit("/", 1)[-1] if ref.startswith("ref:") else "HEAD"


def active_game(base=None):
    """the active game: PARALLAX_GAME / KIT_GAME, else games/.active, else none"""
    g = env("GAME")
    if g:
        return None if g == "none" else g
    try:
        with open(os.path.join(base or root(), "games", ".active"), encoding="utf-8") as fh:
            t = fh.read().strip()
        return t or None
    except OSError:
        return None


def harness():
    if env("HARNESS"):
        return env("HARNESS")
    if os.environ.get("CLAUDECODE") or os.environ.get("CLAUDE_CODE_ENTRYPOINT"):
        return "claude-code"
    if os.environ.get("GEMINI_CLI"):
        return "gemini"
    if os.environ.get("CODEX_SANDBOX") or os.environ.get("CODEX_HOME"):
        return "codex"
    return "shell"


def read(base=None):
    try:
        with open(path(base), encoding="utf-8") as fh:
            s = json.load(fh)
        return s if isinstance(s, dict) else None
    except (OSError, ValueError):
        return None


def write(s, base=None):
    p = path(base)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(s, fh, indent=1, ensure_ascii=False)
    os.replace(tmp, p)
    return p


ACTIVE, ANY = "<active>", "<any>"  # problems(game=...): the checkout's active game (default) / no game check


def packets_dir(base=None):
    """where PROMPT-X keeps every compiled packet by its sha (kit/prompt/evolve.py save_packet)"""
    traces = os.environ.get("KIT_PROMPT_TRACES") or os.path.join(base or root(), "build", "prompt", "traces.json")
    return os.path.join(os.path.dirname(traces), "packets")


def packet_matches(sha, base=None):
    """is there a compiled packet build/prompt/packets/<sha>.json whose prompt really hashes to sha? (a session token
    typed by hand names none)"""
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{6,40}", sha):
        return False
    try:
        with open(os.path.join(packets_dir(base), f"{sha}.json"), encoding="utf-8") as fh:
            packet = json.load(fh)
    except (OSError, ValueError):
        return False
    text = packet.get("orchestrator_prompt") if isinstance(packet, dict) else None
    return isinstance(text, str) and hashlib.sha1(text.encode("utf-8")).hexdigest()[: len(sha)] == sha


def problems(s, session_id=None, base=None, now=None, game=ACTIVE):
    """why a session is NOT fresh -> [reasons] ([] = fresh). game: the game the work is in (None = the project root),
    ACTIVE = the checkout's active game, ANY = not checked (the kit's own files belong to no game)"""
    if not s:
        return ["no .verify/parallax_session.json"]
    out = []
    if s.get("schema") != SCHEMA:
        out.append(f"schema {s.get('schema')!r}")
    started = _parse_iso(s.get("started_at"))
    t = now or datetime.datetime.now(datetime.timezone.utc)
    if started is None:
        out.append("no started_at")
    elif (t - started).total_seconds() > float(s.get("ttl_seconds") or TTL):
        out.append("expired (older than its ttl)")
    if not s.get("prompt_sha"):
        out.append("no prompt_sha (compile the request with PROMPT-X)")
    elif not packet_matches(s["prompt_sha"], base):
        out.append(f"prompt_sha {s['prompt_sha']} names no compiled PROMPT-X packet (a hand-written token)")
    b = branch(base)
    if s.get("branch") and b and s["branch"] != b:
        out.append(f"made on branch {s['branch']}, the checkout is on {b}")
    if game != ANY:
        g = active_game(base) if game == ACTIVE else (game or None)
        if (s.get("game") or None) != g:
            out.append(f"made for game {s.get('game')!r}, this work is in {g or 'the project root'!r}")
    if session_id and s.get("session_id") and s["session_id"] != session_id:
        out.append("another harness session's token")
    return out


def fresh(s=None, session_id=None, base=None):
    return not problems(s if s is not None else read(base), session_id, base)


def stamp(packet, packet_path, prompt_sha, lane=None, model=None, session_id=None, base=None):
    """write (or refresh) the session after a PROMPT-X compile -> the session dict. A refresh of the same session
    keeps what it touched and its skips; a new one starts clean."""
    old = read(base) or {}
    same = bool(old) and not problems(old, session_id, base) and old.get("lane") == lane
    contracts = packet.get("case_contracts") or []
    s = {
        "schema": SCHEMA,
        "started_at": old["started_at"] if same else now_iso(),
        "refreshed_at": now_iso(),
        "ttl_seconds": TTL,
        "session_id": session_id or env("SESSION_ID") or (old.get("session_id") if same else None),
        "branch": branch(base),
        "game": active_game(base),
        "harness": harness(),
        "model": model or packet.get("target_model"),
        "lane": lane or (contracts[0]["lane"] if contracts else (packet.get("lanes") or [None])[0]),
        "lanes": list(packet.get("lanes") or []),
        "prompt_packet": packet_path.replace("\\", "/") if packet_path else None,
        "prompt_sha": prompt_sha,
        "case_contracts": contracts,
        "touched_pipeline_files": list(old.get("touched_pipeline_files") or []) if same else [],
        "skipped_tools": list(old.get("skipped_tools") or []) if same else [],
        "maintenance": list(old.get("maintenance") or []) if same else [],
        "reminded_at": old.get("reminded_at") if same else None,
        "verify_passed_at": None,
        "handoff_written_at": None,
    }
    if same:  # (a re-compile inside the session started at its first compile)
        s["started_at"] = old.get("started_at") or s["started_at"]
    write(s, base)
    return s


def log(field, entry, base=None):
    """append an entry to one of the session's lists (skipped_tools, maintenance, touched_pipeline_files) -> bool"""
    s = read(base)
    if not s:
        return False
    items = list(s.get(field) or [])
    if entry not in items:
        items.append(entry)
    s[field] = items
    write(s, base)
    return True


def mark(field, base=None):
    """verify_passed_at / handoff_written_at = now (kit verify passed, kit handoff written)"""
    s = read(base)
    if not s:
        return False
    s[field] = now_iso()
    write(s, base)
    return True


def git_branch_slow(base=None):
    """(only for tests and tools that may spawn git)"""
    try:
        return subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=base or root(), capture_output=True,
                              text=True, timeout=10).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None
