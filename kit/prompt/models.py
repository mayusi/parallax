"""models.py - the PromptPacket v1 (LIMITATIONS_FIXES_V4 13.7 item 2), the token counter every budget is held to, and
the shared loaders (a profile, a lane template, the repo root).

The counter is a deterministic stand-in for a model tokenizer (none is shipped offline): the larger of characters / 4
and words x 1.33, rounded up. It over-counts plain prose a little, so a packet under its cap here is under it for the
real tokenizers too (IFScale, arXiv:2507.11538: rule compliance falls as instructions grow)."""

import json
import math
import os
import re
from dataclasses import asdict, dataclass, field

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
LANES = ("3d", "vfx", "anim", "world", "ui", "sfx", "systems")
MODELS = ("claude", "codex", "gemini", "local")
TOOLS = ("flux2", "qwen_edit", "trellis2")
# the vault's folder for a lane (systems work is filed under code)
VAULT_LANE = {"systems": "code"}

_WORD = re.compile(r"\S+")


def count_tokens(text):
    """a conservative token estimate: max(chars / 4, words * 1.33), rounded up"""
    text = text or ""
    words = len(_WORD.findall(text))
    return int(math.ceil(max(len(text) / 4.0, words * 1.33)))


def root():
    return os.environ.get("PARALLAX_ROOT") or os.environ.get("KIT_ROOT") or ROOT


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def core_profile():
    """profiles.core of the project config (parallax.config.json, else kit.config.json - the files kit/lib/config.luau
    reads): the project's own exclude_games / exclude_dossiers / exclude_patterns. {} when none (the kit ships none)"""
    for name in ("parallax.config.json", "kit.config.json"):
        path = os.path.join(root(), name)
        if not os.path.isfile(path):
            continue
        try:
            core = ((load_json(path) or {}).get("profiles") or {}).get("core") or {}
        except (OSError, ValueError, AttributeError):
            core = {}
        return core if isinstance(core, dict) else {}
    return {}


def profile(name):
    path = os.path.join(HERE, "profiles", f"{name}.json")
    if not os.path.isfile(path):
        raise ValueError(f"no PROMPT-X profile '{name}' (have: {', '.join(MODELS + TOOLS)})")
    return load_json(path)


def template(lane):
    """a lane template (KIT_PROMPT_TEMPLATES points at another folder: the self-test's broken copies)"""
    folder = os.environ.get("KIT_PROMPT_TEMPLATES") or os.path.join(HERE, "templates")
    path = os.path.join(folder, f"{lane}.json")
    if not os.path.isfile(path):
        raise ValueError(f"no PROMPT-X template for lane '{lane}' (have: {', '.join(LANES)})")
    return load_json(path)


def templates():
    return {lane: template(lane) for lane in LANES}


@dataclass
class PromptPacket:
    """PromptPacket v1: what `kit prompt compile` hands an orchestrator (and its tools)"""

    raw_prompt: str
    target_model: str = "claude"
    lanes: list = field(default_factory=list)
    ambiguity: dict = field(default_factory=lambda: {"score": 0.0, "questions": []})
    repo_grounding: dict = field(default_factory=dict)
    orchestrator_prompt: str = ""
    tool_subprompts: dict = field(default_factory=dict)
    done_when: list = field(default_factory=list)
    token_count: int = 0
    profile: str = "claude"
    schema: int = 1
    answers: dict = field(default_factory=dict)
    auto_filled: dict = field(default_factory=dict)
    pruned: list = field(default_factory=list)
    lane_briefs: dict = field(default_factory=dict)

    def to_dict(self):
        d = asdict(self)
        order = ["schema", "raw_prompt", "target_model", "profile", "lanes", "ambiguity", "answers", "auto_filled"]
        return {k: d[k] for k in order} | {k: v for k, v in d.items() if k not in order}
