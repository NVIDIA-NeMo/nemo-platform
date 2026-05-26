"""Integration smoke test: actually invokes `claude` headlessly.

Skipped when claude is not installed. Designed to also work when run from
*inside* a Claude Code session — that's the nested-invocation case the
library must support.

Run via: `uv run --frozen pytest packages/coding_agents/tests/integration -v`
"""

import shutil
from pathlib import Path

import pytest
from coding_agents import ClaudeCodeAgent, PermissionMode, PermissionPolicy
from coding_agents.events import ResultEvent

pytestmark = pytest.mark.skipif(shutil.which("claude") is None, reason="claude CLI not installed")


@pytest.mark.asyncio
async def test_check_available():
    agent = ClaudeCodeAgent()
    availability = await agent.check_available()
    assert availability.installed
    assert availability.authenticated
    assert availability.version is not None


@pytest.mark.asyncio
async def test_one_shot_run(tmp_path: Path):
    agent = ClaudeCodeAgent(work_root=tmp_path / "work")
    result = await agent.run(
        "Reply with exactly the three words: hello from subprocess",
        working_dir=tmp_path,
        timeout=60,
        permissions=PermissionPolicy(mode=PermissionMode.BYPASS),
        extra_cli_args=["--no-session-persistence"],
    )
    assert isinstance(result, ResultEvent)
    assert result.success, f"agent reported failure: {result}"
    assert result.text is not None
    assert "hello" in result.text.lower()
    assert result.cost_usd > 0
    assert result.duration_ms > 0
    assert result.session_id
    assert result.artifact_dir.is_dir()
    assert (result.artifact_dir / "turn_0000.jsonl").is_file()


@pytest.mark.asyncio
async def test_resume_with_file_write_then_read(tmp_path: Path):
    """Tool-use across resumed turns: first turn writes a .env file via Bash,
    second turn (resumed) reads it back. Validates that the agent's tool use
    actually affects working_dir AND that resume continues the conversation
    in the same working_dir."""
    agent = ClaudeCodeAgent(work_root=tmp_path / "work")

    # First turn: write a .env file. Bypass permissions so Bash tool is allowed.
    r1 = await agent.run(
        "Use the Bash tool to write the single line 'LIFE_THE_UNIVERSE_EVERYTHING=42' to a file "
        "named .env in the current directory. Then reply with just 'done'.",
        working_dir=tmp_path,
        timeout=120,
        permissions=PermissionPolicy(mode=PermissionMode.BYPASS),
    )
    assert r1.success, f"first turn failed: {r1}"
    env_file = tmp_path / ".env"
    assert env_file.exists(), "agent did not create the .env file"
    assert "LIFE_THE_UNIVERSE_EVERYTHING=42" in env_file.read_text()

    # Second turn (resumed): read it back. Asks vaguely so the agent has to
    # rely on conversation context to know which file/variable we mean.
    r2 = await agent.run(
        "Read the .env file you just wrote and reply with just the numeric value of the variable you set.",
        working_dir=tmp_path,
        timeout=120,
        permissions=PermissionPolicy(mode=PermissionMode.BYPASS),
        resume_session_id=r1.session_id,
    )
    assert r2.success, f"resumed turn failed: {r2}"
    assert r2.session_id == r1.session_id
    assert "42" in (r2.text or ""), f"resumed turn lost context: {r2.text!r}"


@pytest.mark.asyncio
async def test_resume_carries_context(tmp_path: Path):
    """Two runs chained via resume_session_id: the second must see what the
    first one was told. Validates that --resume actually wires up context."""
    agent = ClaudeCodeAgent(work_root=tmp_path / "work")

    # First turn: tell the agent a fact. Do NOT use --no-session-persistence
    # here, because the second call needs Claude to find this session on disk.
    r1 = await agent.run(
        "Remember the number 42. Reply with only 'OK'.",
        working_dir=tmp_path,
        timeout=60,
        permissions=PermissionPolicy(mode=PermissionMode.BYPASS),
    )
    assert r1.success, f"first turn failed: {r1}"
    assert r1.session_id

    # Second turn: resume the same session and ask about the fact.
    r2 = await agent.run(
        "What number did I ask you to remember? Reply with just the number.",
        working_dir=tmp_path,
        timeout=60,
        permissions=PermissionPolicy(mode=PermissionMode.BYPASS),
        resume_session_id=r1.session_id,
    )
    assert r2.success, f"resumed turn failed: {r2}"
    assert r2.session_id == r1.session_id
    assert "42" in (r2.text or ""), f"resumed turn lost context: {r2.text!r}"
