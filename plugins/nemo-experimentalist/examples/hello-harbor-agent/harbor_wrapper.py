# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Harbor adapter for the agent in this directory.

`HarborEvaluatorConfig.import_path` defaults to `harbor_wrapper:WrappedAgent`, so
Harbor imports this module out of whichever `agents/agent-N/` directory is being
evaluated and drives the agent through `setup()` then `run()`.

Artifact contract — the agent just writes to two directories and Harbor collects
them into the trial's `artifacts/` directory on the host:
  - `/app/artifacts` -> `artifacts/output/`, declared by `artifacts = [...]` in
    each task.toml.
  - `/app/traces`    -> `artifacts/traces/`, injected automatically by
    `HarborEvaluator._run` via `_with_trace_artifact`.
Nothing needs to be copied by hand.
"""

from __future__ import annotations

import fnmatch
import logging
import shlex
from pathlib import Path

from harbor import AgentContext, BaseAgent, BaseEnvironment

logger = logging.getLogger(__name__)

AGENT_DIR = Path(__file__).parent

# Never uploaded into the task container: optimizer bookkeeping, caches, the
# dataset itself, and anything holding credentials.
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


class WrappedAgent(BaseAgent):
    """Upload this agent directory into the container and run one task."""

    @staticmethod
    def name() -> str:
        return "hello-harbor-agent"

    def version(self) -> str | None:
        return "1.0.0"

    async def setup(self, environment: BaseEnvironment) -> None:
        """Upload the agent's source files. No dependency install: stdlib only."""
        for entry in AGENT_DIR.iterdir():
            name = entry.name
            if name in EXCLUDE or any(fnmatch.fnmatch(name, pattern) for pattern in EXCLUDE_GLOB):
                continue
            if entry.is_file():
                await environment.upload_file(entry, f"/app/{name}")
            elif entry.is_dir():
                await environment.upload_dir(entry, f"/app/{name}")
        logger.info("[setup] uploaded agent sources to /app")

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        """Execute the agent on *instruction* inside the task container."""
        session_id = self.session_id or "local"
        proc = await environment.exec(
            f"cd /app && python main.py --prompt {shlex.quote(instruction.strip())} "
            f"--session-id {shlex.quote(session_id)}"
        )

        # Nothing is copied here: Harbor collects /app/artifacts and /app/traces
        # after this method returns, per the declarations described above.
        context.metadata = {
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "returncode": proc.return_code,
        }
        if proc.return_code != 0:
            raise RuntimeError(f"Agent process failed with exit code {proc.return_code}: {proc.stderr or proc.stdout}")
