# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Result types for ``nemo eval-author discover``.

The command exists so that a later, cheaper model can run a Harbor eval without
rediscovering anything, which only works if every claim in the output is traceable to
whoever established it. That is what ``Finding.harbor_call`` and ``Finding.provenance``
are for: a reader can tell a verdict Harbor's own code returned from a path we merely
observed on disk, and both from something a language model guessed. A report whose
findings are all ``provenance="inference"`` is a report to distrust.

Shaped after ``CheckResult`` in ``nemo_insights_plugin.contracts.checks`` but defined
here, because a finding carries the artifact it is about and the Harbor call that judged
it, and a readiness check carries neither.
"""

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

FILESET_NAME = "nemo-eval-author"
"""One fixed fileset with agent-scoped paths, following the telemetry precedent."""

JOB_CONFIG_FILENAME = "harbor-job.yaml"
REPORT_FILENAME = "discovery.md"

Status = Literal["pass", "warn", "fail"]

Provenance = Literal["harbor", "filesystem", "inference"]
"""Who established a finding.

``harbor``     a Harbor API or CLI returned this verdict, so it is as true as the run
               would be. Always paired with ``harbor_call``.
``filesystem`` we observed it directly (a file exists, a name matched).
``inference``  the scout proposed it. Never load-bearing on its own: a proposal has to
               come back through the validation ladder before it can be persisted.
"""

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
    provenance: Provenance = "filesystem"


class ConfigSource(BaseModel):
    """The winning source, kept so a reader knows how much to trust the config."""

    kind: SourceKind
    detail: str
    path: Path | None = None
    adjusted: bool = Field(
        default=False,
        description="Whether the validated payload has diverged from the file at ``path``.",
    )

    @property
    def rank(self) -> int:
        return SOURCE_PRIORITY.index(self.kind)

    @property
    def owns_file(self) -> bool:
        """Whether the repo maintains the config file we validated, unchanged.

        The one case where discovery has nothing of its own to persist: the file already
        exists, someone maintains it, and Harbor accepted exactly its contents. Shipping a
        second copy would create a config nobody owns and that drifts the moment the real
        one is edited. ``prior_job`` is excluded even though it has a path, because that
        path is a record Harbor wrote inside a job's output directory rather than an input
        anyone maintains.
        """
        return self.kind == "config_file" and self.path is not None and not self.adjusted


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

    ``location`` spares the reader from deciding which case they are in: ``repo`` means the
    path is relative to ``repo_root`` and already on disk, ``fileset`` means it is a remote
    path in ``FILESET_NAME`` to fetch first.
    """

    location: Literal["repo", "fileset"]
    path: str


class RequiredEnvVar(BaseModel):
    """A host variable a task config templates as ``${VAR}`` or ``${VAR:-default}``.

    Discover records the name and where it was declared. Whether this machine has a
    value for it is ``doctor``'s question, not ours.
    """

    name: str
    default: str | None = None
    declared_in: Path


class InputFingerprint(BaseModel):
    """A file the report was derived from, so a re-run can tell what moved."""

    path: str
    sha256: str


def digest_inputs(inputs: list[InputFingerprint]) -> str:
    """Hash a set of input fingerprints, order-independently.

    A free function and not just a property, because the freshness check runs it against
    the inputs a *previous* report listed, before this run has a report of its own. Both
    sides must hash identically or the comparison is meaningless, so there is one
    implementation. Canonical JSON matches the digest style in ``materialization.py``.
    """
    payload = [[item.path, item.sha256] for item in sorted(inputs, key=lambda item: item.path)]
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


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
    inputs: list[InputFingerprint] = Field(default_factory=list)
    discovered_at: datetime
    last_validated_at: datetime

    @property
    def blocking(self) -> list[Finding]:
        return [finding for finding in self.findings if finding.status == "fail"]

    @property
    def inputs_digest(self) -> str:
        """One hash over every input, so a re-run can skip the ladder in a single compare.

        Derived rather than stored: a digest that can disagree with the list it summarizes
        is worse than no digest, because the whole point is deciding whether to trust the
        file without redoing the work.
        """
        return digest_inputs(self.inputs)

    @property
    def runnable(self) -> bool:
        """True only when a config was found and nothing about it failed.

        The whole artifact turns on this flag, so it stays conservative: no source means
        not runnable even with an empty failure list, because there is nothing to run.
        """
        return self.config_source is not None and not self.blocking
