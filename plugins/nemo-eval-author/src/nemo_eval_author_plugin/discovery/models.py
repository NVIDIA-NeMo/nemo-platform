# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Result types for ``nemo eval-author discover``.

``Finding.harbor_call`` names the Harbor API or CLI that returned a verdict. A finding
without one was observed directly rather than judged by Harbor, which is the difference
between "Harbor rejected this config" and "we read this off the filesystem". Both the CLI
and the report render the call, so the distinction reaches the reader.
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

FILESET_NAME = "nemo-eval-author"
"""One fixed fileset with agent-scoped paths, following the telemetry precedent."""

JOB_CONFIG_FILENAME = "harbor-job.yaml"
REPORT_FILENAME = "discovery.md"

Status = Literal["pass", "warn", "fail"]

SourceKind = Literal["config_file", "prior_job", "profile", "convention"]
"""Where a candidate job config came from.

Ordered by how much of it Harbor already agreed to, which is what
``SOURCE_PRIORITY`` encodes:

``config_file`` a config file in the repo; the user declared this.
``prior_job``   ``config.json`` from a job Harbor resolved and ran. Evidence, not a guess.
``profile``     assembled from ``optimizer.yaml`` plus the agent wrapper.
``convention``  assembled from directory layout alone. Weakest, so say so out loud.
"""

SOURCE_PRIORITY: tuple[SourceKind, ...] = ("config_file", "prior_job", "profile", "convention")


class Finding(BaseModel):
    """One thing discover learned, and who vouches for it."""

    name: str
    group: str
    status: Status
    message: str
    path: Path | None = None
    hint: str | None = None
    harbor_call: str | None = Field(
        default=None,
        description="The Harbor API or CLI that returned this verdict, when one did.",
    )


class ConfigSource(BaseModel):
    """The winning source, kept so a reader knows how much to trust the config."""

    kind: SourceKind
    detail: str
    path: Path | None = None

    @property
    def rank(self) -> int:
        return SOURCE_PRIORITY.index(self.kind)

    @property
    def owns_file(self) -> bool:
        """Whether the repo maintains the config file we validated.

        The one case where discovery has nothing of its own to persist: the file already
        exists, someone maintains it, and Harbor accepted exactly its contents. ``prior_job``
        is excluded even though it has a path, because that path is a record Harbor wrote
        inside a job's output directory rather than an input anyone maintains.
        """
        return self.kind == "config_file" and self.path is not None


class CandidateConfig(BaseModel):
    """An unvalidated Harbor job config payload plus where it came from.

    Deliberately a raw ``dict`` rather than a ``JobConfig``. Assembling and judging are
    separate jobs here: if this held a parsed ``JobConfig`` then the schema rung of the
    ladder would have already run somewhere off to the side, and "no config reaches the
    artifact unless a Harbor validator accepted it" would stop being checkable.
    """

    data: dict[str, Any]
    source: ConfigSource


class RunTarget(BaseModel):
    """The config a later run passes to ``harbor job start -c``, and where to get it.

    Harbor runs local task directories through ``-c`` and no other way: ``--dataset`` and
    ``--task`` name registry packages, so a filesystem path handed to either is read as a
    package reference. A repo full of task dirs and no config file therefore cannot be run
    as-is, which is why discovery writes one when the repo does not.
    """

    location: Literal["repo", "fileset"]
    path: str


class RequiredEnvVar(BaseModel):
    """A host variable a task config templates as ``${VAR}`` or ``${VAR:-default}``."""

    name: str
    default: str | None = None
    declared_in: Path


class DiscoveryReport(BaseModel):
    """Everything a later run needs to trust or redo this discovery."""

    schema_version: int = 1
    agent: str
    workspace: str
    repo_root: Path
    harbor_version: str = Field(
        description="A validation result is only as good as the Harbor that produced it, "
        "which is why Harbor stamps its own version into lock.json.",
    )
    config_source: ConfigSource | None = None
    findings: list[Finding] = Field(default_factory=list)
    required_env_vars: list[RequiredEnvVar] = Field(default_factory=list)
    discovered_at: datetime

    @property
    def blocking(self) -> list[Finding]:
        return [finding for finding in self.findings if finding.status == "fail"]

    @property
    def runnable(self) -> bool:
        """True only when a config was found and nothing about it failed.

        The whole artifact turns on this flag, so it stays conservative: no source means
        not runnable even with an empty failure list, because there is nothing to run.
        """
        return self.config_source is not None and not self.blocking
