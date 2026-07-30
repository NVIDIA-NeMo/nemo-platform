# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Orchestration for ``nemo eval-author discover``.

Assemble a candidate config, let Harbor judge it, scout only if that fails on something a
look at the repo could settle, then persist. Sequenced so the expensive and side-effecting
work happens as late and as rarely as possible: the freshness check can skip the ladder
entirely, and the scout runs only after the ladder has failed.

Kept apart from ``cli.py`` so it can be tested without a ``CliRunner`` and so the CLI holds
nothing but flags, printing, and the exit code. ``make_client`` is a module global for the
same reason it is in ``eval_author/run.py``: tests replace it.
"""

import logging
import re
import tempfile
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path

from nemo_eval_author_plugin.discovery import memory, report, scan, sources, validate
from nemo_eval_author_plugin.discovery.models import (
    CandidateConfig,
    DiscoveryReport,
    Finding,
    digest_inputs,
)
from nemo_eval_author_plugin.discovery.validate import ValidationOutcome
from nemo_experimentalist_plugin.client import make_client
from nemo_insights_plugin.contracts.profile import discover_profile
from nemo_platform import AsyncNeMoPlatform

logger = logging.getLogger(__name__)

_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


@dataclass
class DiscoverOptions:
    """Everything the CLI passes through, resolved."""

    repo_root: Path
    agent: str | None = None
    workspace: str = "default"
    base_url: str | None = None
    env_backend: str | None = None
    deep: bool = True
    refresh: bool = False
    dry_run: bool = False


@dataclass
class DiscoverResult:
    """The artifacts, plus what the command needs to report and exit on."""

    report: DiscoveryReport
    markdown: str
    job_config: str | None = None
    persisted: bool = False
    reused: bool = False
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
    """Run discovery end to end."""
    repo_root = options.repo_root.resolve()
    agent = options.agent or _infer_agent_name(repo_root)
    client = make_client(options.base_url)
    try:
        return await _discover(client, options, repo_root=repo_root, agent=agent)
    finally:
        await client.close()


async def _discover(
    client: AsyncNeMoPlatform, options: DiscoverOptions, *, repo_root: Path, agent: str
) -> DiscoverResult:
    prior = await memory.load_previous(client, agent=agent, workspace=options.workspace)

    reuse = _reusable(prior, repo_root, refresh=options.refresh)
    if reuse is not None:
        return await _reuse(client, options, agent=agent, prior=reuse)

    candidate, findings = sources.find_candidate(repo_root, env_backend=options.env_backend)
    outcome = ValidationOutcome()
    if candidate is not None:
        outcome = await validate.run_ladder(candidate, repo_root)
        if not outcome.runnable and options.deep:
            candidate, outcome, scout_findings = await _scout(candidate, outcome, repo_root)
            findings.extend(scout_findings)

    findings.extend(outcome.findings)
    findings.extend(await _probe_repo(client, repo_root, agent=agent, workspace=options.workspace))

    job_config = None
    if outcome.config is not None:
        job_config = report.render_job_config(outcome.config, repo_root)
        findings.append(_round_trip(job_config, repo_root))

    record = report.build_report(
        agent=agent,
        workspace=options.workspace,
        repo_root=repo_root,
        candidate=candidate,
        findings=findings,
        required_env_vars=outcome.required_env_vars,
        inputs=report.fingerprint_inputs(_input_paths(repo_root, candidate, outcome), repo_root),
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
        workspace=options.workspace,
        markdown=markdown,
        job_config=publishable,
    )
    return DiscoverResult(
        report=record,
        markdown=markdown,
        job_config=job_config,
        persisted=persisted,
        memory_findings=memory_findings,
    )


def _reusable(prior: memory.PriorRecord | None, repo_root: Path, *, refresh: bool) -> memory.PriorRecord | None:
    """Whether the prior report still describes this repo, so the ladder can be skipped.

    Only ever reuses a report that was runnable. A prior failure is worth re-deriving even
    on identical inputs, because the reason it failed may have been the machine rather than
    the repo: Docker was not running, a cloud extra was missing.
    """
    if prior is None or refresh or not prior.runnable or not prior.inputs:
        return None
    if digest_inputs(memory.rehash_prior_inputs(prior, repo_root)) != prior.inputs_digest:
        return None
    return prior


async def _reuse(
    client: AsyncNeMoPlatform, options: DiscoverOptions, *, agent: str, prior: memory.PriorRecord
) -> DiscoverResult:
    """Restamp and reupload a report whose inputs have not moved."""
    now = datetime.now(UTC)
    restamped = memory.restamp(prior.text, when=now, harbor_version=report.harbor_version())
    if restamped is None:
        logger.debug("prior report could not be restamped; falling through to a full discovery")
        return await _discover(
            client,
            replace(options, refresh=True),
            repo_root=options.repo_root.resolve(),
            agent=agent,
        )

    front = memory.parse_front_matter(restamped) or {}
    record = DiscoveryReport.model_validate(
        {
            "agent": agent,
            "workspace": options.workspace,
            "repo_root": front.get("repo_root", str(options.repo_root)),
            "harbor_version": front.get("harbor_version", report.harbor_version()),
            "config_source": front.get("config_source"),
            "discovered_at": front.get("discovered_at", now),
            "last_validated_at": now,
            "inputs": [item.model_dump() for item in prior.inputs],
        }
    )
    if options.dry_run:
        return DiscoverResult(report=record, markdown=restamped, reused=True, dry_run=True)

    persisted, memory_findings = await memory.persist(
        client,
        agent=agent,
        workspace=options.workspace,
        markdown=restamped,
        # The stored config is already correct and already uploaded; rewriting it would
        # churn the fileset to produce identical bytes.
        job_config=None,
    )
    return DiscoverResult(
        report=record,
        markdown=restamped,
        persisted=persisted,
        reused=True,
        memory_findings=[item for item in memory_findings if item.name != "upload" or item.status != "warn"],
    )


async def _scout(
    candidate: CandidateConfig, outcome: ValidationOutcome, repo_root: Path
) -> tuple[CandidateConfig, ValidationOutcome, list[Finding]]:
    """Hand a failed ladder to the scout, importing it only if we actually need it.

    The import builds an LLM client while the module's class body executes, so deferring it
    is what keeps ``discover`` usable on a healthy repo with no ``AUTHOR_*`` credentials.
    """
    from nemo_eval_author_plugin.discovery.agent import attempt_repair, is_scoutable

    if not is_scoutable(outcome):
        return candidate, outcome, []
    return await attempt_repair(candidate, outcome, repo_root)


async def _probe_repo(client: AsyncNeMoPlatform, repo_root: Path, *, agent: str, workspace: str) -> list[Finding]:
    _, doctrine = scan.find_doctrine(repo_root)
    _, skills = scan.find_skills(repo_root)
    traces = await scan.probe_traces(client, agent=agent, workspace=workspace)
    return [doctrine, skills, traces]


def _round_trip(job_config: str, repo_root: Path) -> Finding:
    """Validate the exact bytes we intend to persist, from a scratch directory.

    Written outside the repo on purpose: discover inspects a repo and must not leave
    anything in it. Harbor loads the config relative to ``cwd``, which the round trip sets
    to the repo root, so the file's own location does not matter.
    """
    with tempfile.TemporaryDirectory(prefix="eval-author-discover-") as scratch:
        config_path = Path(scratch) / report.JOB_CONFIG_FILENAME
        config_path.write_text(job_config, encoding="utf-8")
        return validate.check_persisted_config(config_path, repo_root)


def _input_paths(repo_root: Path, candidate: CandidateConfig | None, outcome: ValidationOutcome) -> list[Path]:
    """Every file a verdict in this report was derived from.

    The freshness check is only as good as this list: a file that shaped a conclusion but
    is missing here means a later run reports "nothing changed" after someone changed it.
    """
    paths: list[Path] = []
    if candidate is not None and candidate.source.path is not None:
        paths.append(candidate.source.path)

    profile = discover_profile(repo_root)
    if profile is not None:
        paths.append(profile)

    for name in ("ETHOS.md", "AGENT-SPEC.md", "README.md"):
        paths.append(repo_root / name)

    for task_dir in outcome.task_dirs:
        paths.append(task_dir / "task.toml")
        paths.extend(sorted((task_dir / "tests").glob("test.*")))

    if outcome.config is not None:
        for agent_config in outcome.config.agents:
            if agent_config.import_path:
                module = agent_config.import_path.split(":", 1)[0].split(".", 1)[0]
                paths.extend(sorted(repo_root.rglob(f"{module}.py")))
    return paths


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
