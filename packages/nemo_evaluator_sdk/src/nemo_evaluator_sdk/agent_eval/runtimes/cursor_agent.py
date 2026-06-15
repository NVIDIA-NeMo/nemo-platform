# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Reference generalized-agent spec for the Cursor Agent CLI (``cursor-agent``).

A *reference* command builder: the driver and evidence contract are stable, but
the CLI's exact flags may drift with upstream releases. Auth is the caller's
concern (inject via env).
"""

from __future__ import annotations

from nemo_evaluator_sdk.agent_eval.runtimes.generalized_agent import GeneralizedAgentSpec, RunArtifacts


class CursorAgentSpec(GeneralizedAgentSpec):
    """Reference command builder for the Cursor Agent CLI (``cursor-agent``)."""

    name = "cursor_agent"
    binary = "cursor-agent"

    def __init__(self, *, model: str | None = None, binary: str = "cursor-agent") -> None:
        self.model = model
        self.binary = binary

    def build_command(self, artifacts: RunArtifacts) -> list[str]:
        command = [
            self.binary,
            "--print",
            "--output-format",
            "text",
            "--workdir",
            str(artifacts.workspace_dir),
        ]
        if self.model is not None:
            command.extend(["--model", self.model])
        return command


__all__ = ["CursorAgentSpec"]
