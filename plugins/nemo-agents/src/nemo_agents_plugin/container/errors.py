# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Domain exceptions for agent packaging.

The packaging pipeline runs from two callers with incompatible failure
contracts: ``nemo agents package`` (exit codes and stderr) and the
``agents.package`` platform job (an exception the jobs controller records
against the step). These exceptions are the shared vocabulary — the CLI
maps them to :class:`typer.Exit`, the job lets them propagate.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path


class AgentPackagingError(Exception):
    """Base class for every packaging failure."""


class ContainerToolingUnavailableError(AgentPackagingError):
    """The optional ``container`` extra (python-on-whales) is not installed."""

    def __init__(self, action: str) -> None:
        super().__init__(
            f"'python-on-whales' is required for {action}.  From the repository root, "
            "install it with:  uv sync --package nemo-agents-plugin --extra container"
        )


class AgentConfigValidationError(AgentPackagingError):
    """The agent config failed pre-build validation."""

    def __init__(self, errors: Sequence[str]) -> None:
        self.errors = list(errors)
        detail = "\n".join(f"  - {err}" for err in self.errors)
        super().__init__(f"Agent config validation failed:\n{detail}")


class ManagedFileConflictError(AgentPackagingError):
    """A transient build artifact would clobber a pre-existing file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(
            f"refusing to overwrite pre-existing file {path}. Rename or remove it and re-run the package command."
        )


class ImageBuildError(AgentPackagingError):
    """``docker build`` failed."""


class ImagePublishError(AgentPackagingError):
    """``docker tag`` or ``docker push`` failed."""
