# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Harbor adapter for the smoke agent.

No dependency install: NOOA is already in the task image. Harbor collects
/app/artifacts (declared by each task.toml) and /app/traces (injected by the
evaluator), so nothing is copied by hand.
"""

from __future__ import annotations

import fnmatch
import logging
import shlex
import shutil
import tempfile
from pathlib import Path

from harbor import AgentContext, BaseAgent, BaseEnvironment

logger = logging.getLogger(__name__)

AGENT_DIR = Path(__file__).parent
TRACE_DIR = "/app/traces"
TRACE_PATH = f"{TRACE_DIR}/trace.jsonl"
REMOTE_PROMPT_PATH = "/logs/agent/instruction.md"

# Never uploaded into the task container: optimizer bookkeeping, caches, and
# anything holding credentials.
#
# Most of these can no longer be siblings -- this file lives in the agent
# directory that `agent_source` points at, which holds the agent and nothing
# else. They are kept because the directory is a candidate workspace at run time
# and can accumulate caches, and because a credential file inside an agent
# directory must not travel regardless of layout.
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
    "scripts",
}
EXCLUDE_GLOB = {"output.*", "*.md"}


class SymlinkedUploadError(RuntimeError):
    """A selected upload path is, or contains, a symlink."""


def _reject_symlinks(entries: list[Path]) -> None:
    """Raise if any selected entry is a symlink or holds one at any depth.

    Args:
        entries: Top-level paths selected for upload.

    Raises:
        SymlinkedUploadError: naming the first offending path.
    """
    for entry in entries:
        offenders = [entry] if entry.is_symlink() else []
        if entry.is_dir() and not entry.is_symlink():
            offenders.extend(child for child in entry.rglob("*") if child.is_symlink())
        if offenders:
            raise SymlinkedUploadError(
                f"refusing to upload {offenders[0]}: it is a symlink, and following it would copy "
                "host files outside the agent directory into the task container"
            )


class WrappedAgent(BaseAgent):
    """Upload this agent directory into the container and run one task."""

    @staticmethod
    def name() -> str:
        """Return the agent name Harbor records for a trial."""
        return "smoke-agent"

    def version(self) -> str | None:
        """Return the agent version Harbor records for a trial."""
        return "1.0.0"

    async def setup(self, environment: BaseEnvironment) -> None:
        """Upload the agent's source files. NOOA is already installed in the image."""
        selected = [
            entry
            for entry in AGENT_DIR.iterdir()
            if entry.name not in EXCLUDE and not any(fnmatch.fnmatch(entry.name, pattern) for pattern in EXCLUDE_GLOB)
        ]
        # Refuse symlinks before uploading anything. upload_dir follows them, so a
        # link anywhere in a selected subtree would copy host files into the
        # container. Scanned up front so a rejection cannot leave a half-populated
        # /app.
        _reject_symlinks(selected)
        for entry in selected:
            if entry.is_file():
                await environment.upload_file(entry, f"/app/{entry.name}")
            elif entry.is_dir():
                await environment.upload_dir(entry, f"/app/{entry.name}")
        logger.info("[setup] uploaded agent sources to /app")

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        """Execute the standard entrypoint inside the task container."""
        prompt_root = Path(tempfile.mkdtemp(prefix="smoke-agent-prompt-"))
        try:
            prompt_path = prompt_root / "instruction.md"
            prompt_path.write_text(instruction, encoding="utf-8")
            await environment.upload_file(prompt_path, REMOTE_PROMPT_PATH)
            proc = await environment.exec(
                "cd /app && python -m main "
                f"--prompt-file {shlex.quote(REMOTE_PROMPT_PATH)} "
                f"--trace-path {shlex.quote(TRACE_PATH)}",
            )
        finally:
            shutil.rmtree(prompt_root, ignore_errors=True)

        # The evaluator collects /app/traces. Task-declared artifacts remain
        # under /app/artifacts for the verifier and normal Harbor collection.
        context.metadata = {
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "returncode": proc.return_code,
        }
        if proc.return_code != 0:
            raise RuntimeError(f"Agent process failed with exit code {proc.return_code}: {proc.stderr or proc.stdout}")
