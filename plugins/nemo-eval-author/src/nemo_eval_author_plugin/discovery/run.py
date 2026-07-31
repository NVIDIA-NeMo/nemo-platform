# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Orchestration for ``nemo eval-author discover``.

Assemble a candidate config, let Harbor judge it, then persist what it concluded.

Kept apart from ``cli.py`` so it can be tested without a ``CliRunner`` and so the CLI holds
nothing but flags, printing, and the exit code. ``make_client`` is a module global for the
same reason it is in ``eval_author/run.py``: tests replace it.
"""

import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from nemo_eval_author_plugin.discovery import memory, report, scan, sources, validate
from nemo_eval_author_plugin.discovery.models import (
    JOB_CONFIG_FILENAME,
    DiscoveryReport,
    Finding,
)
from nemo_eval_author_plugin.discovery.validate import ValidationOutcome
from nemo_experimentalist_plugin.client import make_client
from nemo_insights_plugin.contracts.profile import discover_profile
from nemo_platform import AsyncNeMoPlatform
from nemo_platform.config.config import Config

_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


@dataclass
class DiscoverOptions:
    """Everything the CLI passes through, resolved.

    Deliberately holds nothing about where the platform is. Which cluster, which
    credentials and which workspace are settled by the active ``nemo`` context, and a repo's
    Harbor environment backend is settled by its own config or Harbor's default. Accepting
    flags for those would let one invocation contradict the config every other command obeys.
    """

    repo_root: Path
    agent: str | None = None
    dry_run: bool = False


@dataclass
class DiscoverResult:
    """The artifacts, plus what the command needs to report and exit on."""

    report: DiscoveryReport
    markdown: str
    job_config: str | None = None
    persisted: bool = False
    dry_run: bool = False
    memory_findings: list[Finding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Exit-zero condition: Harbor can run it and the record was written.

        Two independent claims, deliberately kept apart. ``runnable`` is Harbor's verdict
        on the config; persistence is whether a later agent will actually find it. A run
        that validates but cannot upload has not delivered what the command promises. A dry
        run is exempt because it was asked not to write anything.
        """
        return self.report.runnable and (self.persisted or self.dry_run)


async def discover(options: DiscoverOptions) -> DiscoverResult:
    """Run discovery end to end.

    One call at a time per process. The validation ladder chdirs into the repo and puts it on
    ``sys.path``, both process-wide, so a second concurrent call would judge the wrong tree. A
    caller that needs several repos at once has to run them in separate processes.
    """
    repo_root = options.repo_root.resolve()
    agent = options.agent or _infer_agent_name(repo_root)
    workspace = _active_workspace()
    # No base_url: the active context supplies the cluster and the credentials for it.
    client = make_client(None)
    try:
        return await _discover(client, options, repo_root=repo_root, agent=agent, workspace=workspace)
    finally:
        await client.close()


def _active_workspace() -> str:
    """The workspace the platform context resolves to.

    Read rather than accepted as a flag, so the artifact lands where every other ``nemo``
    command in this context looks. The report records the answer, since a later agent needs
    to name a workspace to fetch from. ``NMP_WORKSPACE`` still overrides, because that is the
    platform's own escape hatch rather than one of ours.
    """
    return Config.load().resolve().workspace


async def _discover(
    client: AsyncNeMoPlatform, options: DiscoverOptions, *, repo_root: Path, agent: str, workspace: str
) -> DiscoverResult:
    candidate, findings = sources.find_candidate(repo_root)
    outcome = ValidationOutcome()
    if candidate is not None:
        outcome = await validate.run_ladder(candidate, repo_root)

    findings.extend(outcome.findings)
    findings.extend(await _probe_repo(client, repo_root, agent=agent, workspace=workspace))

    # When the repo maintains the config Harbor accepted, that file is what a later run will
    # pass to -c, so it is the thing worth round-tripping and there is nothing of ours to
    # persist. Rendering a copy anyway would put a second config in the fileset that no one
    # owns and that goes stale the moment the real one is edited.
    repo_config = candidate.source.path if candidate is not None and candidate.source.owns_file else None
    job_config = None
    if repo_config is not None:
        findings.append(validate.check_config_file(repo_config, repo_root))
    elif outcome.config is not None:
        job_config = report.render_job_config(outcome.config, repo_root)
        findings.append(_round_trip(job_config, repo_root))

    record = report.build_report(
        agent=agent,
        workspace=workspace,
        repo_root=repo_root,
        candidate=candidate,
        findings=findings,
        required_env_vars=outcome.required_env_vars,
    )
    # A config only travels with a report that vouches for it. The schema rung can pass
    # while a later rung fails, and shipping the config anyway would put a file in the
    # fileset that reads as ready to run.
    publishable = job_config if record.runnable else None
    markdown = report.render_markdown(record)

    if options.dry_run:
        return DiscoverResult(report=record, markdown=markdown, job_config=job_config, dry_run=True)

    persisted, memory_findings = await memory.persist(
        client,
        agent=agent,
        workspace=workspace,
        markdown=markdown,
        job_config=publishable,
    )
    if job_config is not None and publishable is None:
        memory_findings.append(
            Finding(
                # Not "upload": withholding is a decision, and memory.persist uses that name
                # for an upload that actually broke.
                name="config-withheld",
                group="memory",
                status="warn",
                message=f"Withheld {JOB_CONFIG_FILENAME}: the config did not clear every check",
                hint="A config in this fileset is always one Harbor could run, so none was written.",
            )
        )
    return DiscoverResult(
        report=record,
        markdown=markdown,
        job_config=job_config,
        persisted=persisted,
        memory_findings=memory_findings,
    )


async def _probe_repo(client: AsyncNeMoPlatform, repo_root: Path, *, agent: str, workspace: str) -> list[Finding]:
    return [
        scan.find_doctrine(repo_root),
        scan.find_skills(repo_root),
        await scan.probe_traces(client, agent=agent, workspace=workspace),
    ]


def _round_trip(job_config: str, repo_root: Path) -> Finding:
    """Validate the exact bytes we intend to persist, from a scratch directory.

    Written outside the repo on purpose: discover inspects a repo and must not leave
    anything in it. Harbor loads the config relative to ``cwd``, which the round trip sets
    to the repo root, so the file's own location does not matter.
    """
    with tempfile.TemporaryDirectory(prefix="eval-author-discover-") as scratch:
        config_path = Path(scratch) / JOB_CONFIG_FILENAME
        config_path.write_text(job_config, encoding="utf-8")
        return validate.check_config_file(config_path, repo_root)


def _infer_agent_name(repo_root: Path) -> str:
    """Name from ``optimizer.yaml`` when it says, else a slug of the directory."""
    profile = discover_profile(repo_root)
    if profile is not None:
        try:
            declared = sources.read_profile_agent(profile)
        except Exception:
            declared = None
        if declared:
            return _slug(declared)
    return _slug(repo_root.name)


def _slug(value: str) -> str:
    slug = _SLUG_PATTERN.sub("-", value.strip().lower()).strip("-")
    return slug or "agent"


__all__ = ["DiscoverOptions", "DiscoverResult", "discover"]
