# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Harbor adapter for the deterministic agent in this fixture directory."""

from __future__ import annotations

import fnmatch
import logging
import shlex
from pathlib import Path

from harbor import AgentContext, BaseAgent, BaseEnvironment

logger = logging.getLogger(__name__)
AGENT_DIR = Path(__file__).parent
EXCLUDE = {
    "eval-and-optimize",
    "__pycache__",
    ".git",
    ".claude",
    ".uv",
    ".venv",
    ".env",
    ".env.example",
    "traces",
    "artifacts",
    "dataset",
}
EXCLUDE_GLOB = {"output.*", "*.md"}


class SymlinkedUploadError(RuntimeError):
    """A selected upload path is, or contains, a symlink."""


def _reject_symlinks(entries: list[Path]) -> None:
    """Reject symlinks so agent upload cannot escape its fixture directory."""
    for entry in entries:
        offenders = [entry] if entry.is_symlink() else []
        if entry.is_dir() and not entry.is_symlink():
            offenders.extend(child for child in entry.rglob("*") if child.is_symlink())
        if offenders:
            raise SymlinkedUploadError(f"refusing to upload {offenders[0]}: it is a symlink")


class WrappedAgent(BaseAgent):
    """Upload this agent directory into the container and run one task."""

    @staticmethod
    def name() -> str:
        return "hello-harbor-agent"

    def version(self) -> str | None:
        return "1.0.0"

    async def setup(self, environment: BaseEnvironment) -> None:
        """Upload the standard-library-only agent sources."""
        selected = [
            entry
            for entry in AGENT_DIR.iterdir()
            if entry.name not in EXCLUDE and not any(fnmatch.fnmatch(entry.name, pattern) for pattern in EXCLUDE_GLOB)
        ]
        _reject_symlinks(selected)
        for entry in selected:
            if entry.is_file():
                await environment.upload_file(entry, f"/app/{entry.name}")
            elif entry.is_dir():
                await environment.upload_dir(entry, f"/app/{entry.name}")
        logger.info("[setup] uploaded agent sources to /app")

    async def run(self, instruction: str, environment: BaseEnvironment, context: AgentContext) -> None:
        """Execute the agent on *instruction* inside the task container."""
        session_id = self.session_id or "local"
        proc = await environment.exec(
            f"cd /app && python main.py --prompt {shlex.quote(instruction.strip())} "
            f"--session-id {shlex.quote(session_id)}"
        )
        context.metadata = {"stdout": proc.stdout, "stderr": proc.stderr, "returncode": proc.return_code}
        context.n_input_tokens = 7
        context.n_output_tokens = 3
        context.n_cache_tokens = 1
        if proc.return_code != 0:
            raise RuntimeError(f"Agent process failed with exit code {proc.return_code}: {proc.stderr or proc.stdout}")
