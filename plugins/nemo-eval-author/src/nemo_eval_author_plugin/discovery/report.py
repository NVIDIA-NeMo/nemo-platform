# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Render the two artifacts discover persists.

``harbor-job.yaml`` is the config a later agent hands to Harbor. ``discovery.md`` is the
record around it: which source won, what every rung of the ladder concluded, what a run
needs from the host, and what is blocking when something is.

The markdown leads with front matter because the first reader is a program: ``runnable``
and ``run_config`` are the whole machine-readable contract, and the body below them is a
short human summary of the same thing.

Paths in the persisted config are rewritten relative to the repo root. An absolute path
would encode this machine into an artifact meant to outlive it, so the config is written to
be run from ``repo_root``, and the front matter records where that is.
"""

from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import yaml
from harbor.models.job.config import JobConfig
from nemo_eval_author_plugin.discovery.models import (
    JOB_CONFIG_FILENAME,
    CandidateConfig,
    DiscoveryReport,
    Finding,
    RequiredEnvVar,
    RunTarget,
)
from nemo_eval_author_plugin.discovery.scan import display_path

_STATUS_MARK = {"pass": "ok", "warn": "warn", "fail": "FAIL"}


def harbor_version() -> str:
    """The Harbor that produced these verdicts.

    A validation result is only as good as the version that returned it, which is why
    Harbor stamps its own version into ``lock.json``. Same reasoning here.
    """
    try:
        return version("harbor")
    except PackageNotFoundError:
        return "unknown"


def build_report(
    *,
    agent: str,
    workspace: str,
    repo_root: Path,
    candidate: CandidateConfig | None,
    findings: list[Finding],
    required_env_vars: list[RequiredEnvVar],
    discovered_at: datetime | None = None,
) -> DiscoveryReport:
    return DiscoveryReport(
        agent=agent,
        workspace=workspace,
        repo_root=repo_root,
        harbor_version=harbor_version(),
        config_source=candidate.source if candidate is not None else None,
        findings=findings,
        required_env_vars=required_env_vars,
        discovered_at=discovered_at or datetime.now(UTC),
    )


def run_target(report: DiscoveryReport) -> RunTarget | None:
    """Which config a later run should pass to ``-c``, or ``None`` when there is none.

    A repo that maintains its own config keeps it: Harbor accepted exactly that file, so the
    artifact points at it rather than shipping a copy that starts drifting the moment
    someone edits the original. Every other source has no such file — the payload is
    discovery's own synthesis — so the fileset is the only place it exists.
    """
    if not report.runnable:
        return None
    source = report.config_source
    if source is not None and source.owns_file and source.path is not None:
        return RunTarget(location="repo", path=display_path(source.path, report.repo_root))
    return RunTarget(location="fileset", path=f"{report.agent}/{JOB_CONFIG_FILENAME}")


def render_job_config(config: JobConfig, repo_root: Path) -> str:
    """Serialize the validated config, with in-repo paths made relative.

    ``exclude_defaults`` keeps the file to what was actually decided, so a reader can tell
    a deliberate setting from a Harbor default. Secrets are safe to write: Harbor's own
    ``AgentConfig.env`` serializer rewrites sensitive values as ``${VAR}`` templates on the
    way out, so the dump carries the variable names a run needs and none of their values.

    ``job_name`` is dropped unless the source config named it. Harbor's default is a
    timestamp generated at load, and freezing one into a reusable artifact would label
    every future run with the moment discovery happened.
    """
    generated = set() if "job_name" in config.model_fields_set else {"job_name"}
    payload = _relativize(config.model_dump(mode="json", exclude_defaults=True, exclude=generated), repo_root)
    return yaml.safe_dump(payload, sort_keys=True, default_flow_style=False)


def render_markdown(report: DiscoveryReport) -> str:
    """The narrative artifact, front matter first."""
    front = yaml.safe_dump(_front_matter(report), sort_keys=False, default_flow_style=False).rstrip()
    body = "\n".join(_body(report))
    return f"---\n{front}\n---\n\n{body}\n"


def _front_matter(report: DiscoveryReport) -> dict[str, Any]:
    source = report.config_source
    target = run_target(report)
    return {
        "schema_version": report.schema_version,
        "agent": report.agent,
        "workspace": report.workspace,
        "repo_root": str(report.repo_root),
        "runnable": report.runnable,
        "config_source": (
            {
                "kind": source.kind,
                "detail": source.detail,
                "path": display_path(source.path, report.repo_root) if source.path else None,
            }
            if source is not None
            else None
        ),
        "run_config": target.model_dump() if target is not None else None,
        "validation": {finding.name: finding.status for finding in report.findings if finding.group == "validation"},
        "harbor_version": report.harbor_version,
        "required_env_vars": [
            {
                "name": item.name,
                "default": item.default,
                "declared_in": display_path(item.declared_in, report.repo_root),
            }
            for item in report.required_env_vars
        ],
        "discovered_at": report.discovered_at.isoformat(),
    }


def _body(report: DiscoveryReport) -> list[str]:
    lines = [f"# Harbor eval setup for `{report.agent}`", ""]
    lines += _verdict_section(report)
    lines += _findings_section(report)
    lines += _env_section(report)
    return lines


def _verdict_section(report: DiscoveryReport) -> list[str]:
    target = run_target(report)
    if target is None:
        lines = ["**Harbor cannot run this repo's evals yet.** Blocking:", ""]
        for finding in report.blocking:
            lines.append(f"- **{finding.name}** — {finding.message}")
            if finding.harbor_call:
                lines.append(f"  - reported by `{finding.harbor_call}`")
            if finding.hint:
                lines.append(f"  - {finding.hint}")
        return [*lines, ""]

    source = report.config_source
    if target.location == "repo":
        config_arg = target.path
        where = f"From `{report.repo_root}`, because the config's paths are relative to it:"
    else:
        config_arg = JOB_CONFIG_FILENAME
        where = f"Fetch `{target.path}` from the `{report.workspace}` workspace into `{report.repo_root}`, then:"

    lines = [
        f"Harbor {report.harbor_version} can run this repo's evals. The config was "
        f"{source.detail if source is not None else 'unknown'}.",
        "",
        where,
        "",
        "```bash",
        f"harbor job start -c {config_arg}",
        "```",
        "",
    ]
    if report.required_env_vars:
        names = " ".join(f"{item.name}=..." for item in report.required_env_vars)
        lines += [f"Set the host variables first: `{names}`", ""]
    return lines


def _findings_section(report: DiscoveryReport) -> list[str]:
    groups = [("validation", "What Harbor checked"), ("repo", "Repo shape")]
    lines: list[str] = []
    for group, heading in groups:
        items = [finding for finding in report.findings if finding.group == group]
        if not items:
            continue
        lines += [f"## {heading}", ""]
        for finding in items:
            call = f" (`{finding.harbor_call}`)" if finding.harbor_call else ""
            lines.append(f"- `{_STATUS_MARK[finding.status]}` **{finding.name}**: {finding.message}{call}")
            if finding.hint:
                lines.append(f"  - {finding.hint}")
        lines.append("")
    return lines


def _env_section(report: DiscoveryReport) -> list[str]:
    if not report.required_env_vars:
        return []
    lines = [
        "## Host variables",
        "",
        "Harbor resolves these from the environment at trial start and raises on a missing one.",
        "",
    ]
    for item in report.required_env_vars:
        default = f", default `{item.default}`" if item.default is not None else ", no default"
        lines.append(f"- `{item.name}`{default} — declared in `{display_path(item.declared_in, report.repo_root)}`")
    return [*lines, ""]


def _relativize(payload: Any, repo_root: Path) -> Any:
    """Rewrite absolute paths under *repo_root* as repo-relative posix strings.

    Applied to the whole dumped structure rather than named fields, because Harbor carries
    paths in several places (datasets, tasks, skills, output dirs) and a config that only
    half-relativizes is worse than one that does not try. Paths outside the repo are left
    alone: they are genuinely elsewhere, and pretending otherwise would break the run.
    """
    prefix = f"{repo_root}/"
    if isinstance(payload, dict):
        return {key: _relativize(value, repo_root) for key, value in payload.items()}
    if isinstance(payload, list):
        return [_relativize(item, repo_root) for item in payload]
    if isinstance(payload, str):
        if payload == str(repo_root):
            return "."
        if payload.startswith(prefix):
            return Path(payload).relative_to(repo_root).as_posix()
    return payload
