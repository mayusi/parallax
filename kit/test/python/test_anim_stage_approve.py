"""`kit approve anim <name> "<words>" --by owner --stage blocking|design --id <id>` (card rpdz; the owner's V3 list,
anim stage A.2): the animation lane's stage approvals in the kit's own approve command, written where the lane's
own --approve writes them. Before: "the anim lane has no stage approvals". Only the refusals are run here (nothing is
written into the project); the yes itself was run once on a probe move by hand (card a77q)."""
import json
import os
import shutil
import subprocess

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))


def kit(*args):
    lune = shutil.which("lune")
    if not lune:
        pytest.skip("lune is not on this machine")
    r = subprocess.run([lune, "run", "kit", *args, "--game", "none"], capture_output=True, text=True, encoding="utf-8",
                       cwd=ROOT, env={**os.environ, "KIT_GAME": "none"}, timeout=300)
    lines = r.stdout.splitlines()
    summary = next((ln[len("summary: "):] for ln in lines if ln.startswith("summary: ")), "")
    return r.returncode, summary


def test_an_animation_stage_is_a_stage_the_approve_command_knows_and_only_the_owner_gives():
    code, said = kit("approve", "anim", "ZzNoSuchMove", "yes", "--stage", "blocking")
    assert code != 0 and "approved only by the owner" in said and "no stage approvals" not in said
    code, said = kit("approve", "anim", "ZzNoSuchMove", "yes", "--by", "owner", "--stage", "blocking")
    assert code != 0 and "--id" in said                                 # which blocking did he see?
    code, said = kit("approve", "anim", "ZzNoSuchMove", "yes", "--by", "owner", "--stage", "pose")
    assert code != 0 and "blocking, design" in said


def test_a_yes_to_a_blocking_that_was_never_made_records_nothing():
    code, said = kit("approve", "anim", "ZzNoSuchMove", "yes", "--by", "owner", "--stage", "blocking", "--id", "0123456789ab")
    assert code != 0 and "nothing recorded" in said and "no blocking" in said
    assert not os.path.exists(os.path.join(ROOT, "assets", "animations", "blocks", "ZzNoSuchMove.blocking.json"))
    code, said = kit("approve", "anim", "ZzNoSuchSet", "yes", "--by", "owner", "--stage", "design", "--id", "0123456789ab")
    assert code != 0 and "nothing recorded" in said
