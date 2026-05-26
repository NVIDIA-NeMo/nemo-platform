import asyncio

import pytest
from coding_agents.claude_code.agent import ClaudeCodeAgent
from coding_agents.errors import PermissionModeUnsafeError
from coding_agents.permissions import PermissionMode, PermissionPolicy


# Locks in the default: a no-arg PermissionPolicy uses BYPASS so out-of-the-box
# `run()` calls don't hang waiting on a permission prompt. If anyone changes
# the default to something interactive, this test breaks loudly.
def test_default_policy_is_bypass():
    policy = PermissionPolicy()
    assert policy.mode == PermissionMode.BYPASS
    assert policy.is_headless_safe()


# PLAN mode is the read-only alternative to BYPASS; also safe because it
# never triggers prompts. Documents that callers have two safe choices.
def test_plan_mode_is_headless_safe():
    assert PermissionPolicy(mode=PermissionMode.PLAN).is_headless_safe()


# The two modes that *would* hang in headless: DEFAULT prompts for every
# tool use, ACCEPT_EDITS prompts for non-edit tools. Both deadlock with
# no TTY. is_headless_safe() must return False for both.
def test_default_and_accept_edits_are_not_headless_safe():
    assert not PermissionPolicy(mode=PermissionMode.DEFAULT).is_headless_safe()
    assert not PermissionPolicy(mode=PermissionMode.ACCEPT_EDITS).is_headless_safe()


# End-to-end guard: calling agent.run() with an unsafe mode must raise
# PermissionModeUnsafeError *before* any subprocess is spawned — so the
# library fails fast instead of hanging.
def test_run_refuses_unsafe_mode(tmp_path):
    agent = ClaudeCodeAgent(work_root=tmp_path / "work")
    with pytest.raises(PermissionModeUnsafeError):
        asyncio.run(
            agent.run(
                "anything",
                working_dir=tmp_path,
                permissions=PermissionPolicy(mode=PermissionMode.DEFAULT),
            )
        )
