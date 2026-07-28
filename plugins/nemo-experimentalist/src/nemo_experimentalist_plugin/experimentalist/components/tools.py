# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import logging
from collections.abc import Sequence
from pathlib import Path

from nemo_experimentalist_plugin.entities import Candidate
from nooa.tools import ShellResult, ShellTools

from .holdout_utils import (
    BLOCKED_MESSAGE,
    DEFAULT_BLOCKED_PATHS,
)

logger = logging.getLogger(__name__)


class GuardedShellTools(ShellTools):
    """``ShellTools`` that refuses shell access to held-out dataset splits.

    The optimizer's sub-agents run CodeAct with a raw shell rooted at the
    workspace, so they could read the held-out validation ground truth straight off disk
    (``cat dataset/validation/.../tests/test.sh``) and overfit the selection
    signal. This intercepts the ``ShellTools.run`` chokepoint and refuses any command that
    references a held-out split.

    It is a tripwire, not a wall: a substring match can be bypassed by a
    determined caller (globs, shell variables, ``find / -name test.sh``). It
    defeats casual and accidental access and logs every attempt. Pair it with the
    ``DatasetTool`` split guard, which covers the separate ``Path.read_text``
    channel that never touches bash.

    Args:
        cwd: Working directory forwarded to ``ShellTools``.
        blocked_paths: Token substrings whose presence in a command causes the
            command to be rejected; defaults to ``DEFAULT_BLOCKED_PATHS``.
        init_command: Optional command run once when the shell session starts.

    """

    def __init__(
        self,
        cwd: str | Path = ".",
        *,
        blocked_paths: Sequence[str] = DEFAULT_BLOCKED_PATHS,
        init_command: str | None = None,
    ) -> None:
        """Initialize with a working directory and an optional set of blocked path tokens."""
        super().__init__(cwd=str(cwd), init_command=init_command)
        self._blocked_paths = tuple(blocked_paths)

    def is_blocked(self, command: str) -> bool:
        """Return True if the command references any held-out split path token.

        Args:
            command: shell command string to inspect.

        Returns:
            bool: True if any blocked path token appears in the command.

        """
        return any(token in command for token in self._blocked_paths)

    async def run(
        self,
        command: str,
        *,
        stdin: str | None = None,
        timeout: float = 30.0,
    ) -> ShellResult:
        """Execute a shell command, blocking access to held-out dataset splits.

        Args:
            command: Shell command string to execute.
            stdin: Optional text piped to stdin.
            timeout: Timeout in seconds; forwarded to ``ShellTools.run``.

        Returns:
            ShellResult: The result of the command, or a synthetic failure result
            with ``returncode=1`` and ``stderr=BLOCKED_MESSAGE`` when the command
            references a held-out split path.

        """
        if self.is_blocked(command):
            logger.warning(f"GuardedShellTools blocked held-out access: {command}")
            return ShellResult(stdout="", stderr=BLOCKED_MESSAGE, returncode=1)
        return await super().run(command, stdin=stdin, timeout=timeout)


class WorkspaceTool:
    """Navigate the eval-and-optimize workspace: agents and analysis files.

    Args:
        workspace: Absolute path to the eval-and-optimize workspace root.

    """

    def __init__(self, workspace: Path) -> None:
        """Initialize the workspace tool for the given workspace."""
        self.workspace = Path(workspace).resolve()
        self._eval_root = self.workspace / "eval-and-optimize"
        self._agents_root = self._eval_root / "agents"
        self._analysis_root = self._eval_root / "analysis"

    # ── Navigation ────────────────────────────────────────────────────────────

    def list_agents(self) -> list[str]:
        """Return all agent IDs that have a ``metadata.json``, sorted naturally.

        Returns:
            list[str]: agent IDs in natural numeric order.

        """
        if not self._agents_root.exists():
            return []
        ids = [d.name for d in self._agents_root.iterdir() if d.is_dir() and (d / "metadata.json").exists()]
        return sorted(
            ids,
            key=lambda s: int(s.split("-")[1]) if s.split("-")[1].isdigit() else 0,
        )

    def get_agent_path(self, agent_id: str) -> str:
        """Return the absolute path to an agent's directory.

        Args:
            agent_id: the agent to locate.

        Returns:
            str: absolute path to the agent's directory under ``eval-and-optimize/agents/``.

        """
        return str(self._agents_root / agent_id)

    # ── File listing ──────────────────────────────────────────────────────────

    def list_agent_files(self, agent_id: str) -> list[str]:
        """Return all files in an agent's directory (relative paths).

        Args:
            agent_id: the agent to inspect.

        Returns:
            list[str]: sorted relative paths of all files in the agent directory.

        """
        agent_dir = self._agents_root / agent_id
        if not agent_dir.exists():
            return []
        return sorted(str(f.relative_to(agent_dir)) for f in agent_dir.rglob("*") if f.is_file())

    # ── File reading ──────────────────────────────────────────────────────────

    def read_agent_file(self, agent_id: str, relative_path: str, limit: int | None = 8000) -> str:
        """Read any file inside an agent's directory by relative path.

        Args:
            agent_id:      e.g. "agent-2"
            relative_path: e.g. "main.py", "metadata.json"
            limit:         max characters (default 8000, None = no truncation)

        Returns:
            str: file contents, truncated to ``limit`` characters if needed, or empty
            string if the file is not found.

        """
        return self._read_file(self._agents_root / agent_id / relative_path, limit=limit)

    def read_analysis_file(self, path_or_round: "str | int", limit: int | None = 8000) -> str:
        """Read a file from eval-and-optimize/analysis/.

        Args:
            path_or_round: round number (e.g. 1 → round-1.md) or filename.
            limit:         max characters (default 8000, None = no truncation)

        Returns:
            str: file contents, truncated to ``limit`` characters if needed, or empty
            string if the file is not found.

        """
        if isinstance(path_or_round, int):
            path = self._analysis_root / f"round-{path_or_round}.md"
        else:
            path = self._analysis_root / path_or_round
        return self._read_file(path, limit=limit)

    def get_metadata(self, agent_id: str) -> Candidate:
        """Read ``agents/{agent_id}/metadata.json`` as a :class:`Candidate`.

        Args:
            agent_id: the agent whose metadata to read.

        Returns:
            Candidate: parsed candidate, or a minimal candidate with default
            values if the file is missing or unreadable.

        """
        from nemo_experimentalist_plugin.experimentalist.experimentalist_backend import (
            LocalExperimentalistBackend,
        )

        path = self._agents_root / agent_id / "metadata.json"
        # Build a throw-away backend instance scoped to the workspace root so we
        # can reuse its deserialization logic without duplicating it here.
        _backend = LocalExperimentalistBackend.__new__(LocalExperimentalistBackend)
        _backend._eo = self._eval_root  # type: ignore[attr-defined]
        if not path.exists():
            raise FileNotFoundError(f"Metadata file not found: {path}")
        return _backend._load_candidate(path)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _read_file(self, path: Path, limit: int | None = 4000) -> str:
        if not path.exists():
            return ""
        try:
            text = path.read_text().strip()
            if limit is not None and len(text) > limit:
                text = text[:limit] + f"... [truncated, {len(text)} chars total]"
            return text
        except (OSError, UnicodeDecodeError):
            return ""
