# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Render the two artifacts discover persists.

``harbor-job.yaml`` is the config a later agent hands to Harbor. ``discovery.md`` is the
story around it: which source won, what every rung of the ladder concluded, what a run
needs from the host, and what is blocking when something is.

The markdown leads with front matter rather than prose because the first reader is a
program. ``runnable`` and ``inputs_digest`` are what let a later run skip everything here:
if the digest still matches and the flag is true, nothing about the repo that produced this
verdict has moved.

Paths in the persisted config are rewritten relative to the repo root. An absolute path
would encode this machine into an artifact meant to outlive it, so the config is written to
be run from ``repo_root``, and the front matter records where that is.
"""

import hashlib
import json
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import yaml
from harbor.models.job.config import JobConfig
from nemo_eval_author_plugin.discovery.models import (
    CandidateConfig,
    DiscoveryReport,
    Finding,
    InputFingerprint,
    RequiredEnvVar,
)
from nemo_eval_author_plugin.discovery.scan import display_path

JOB_CONFIG_FILENAME = "harbor-job.yaml"
REPORT_FILENAME = "discovery.md"

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


def fingerprint_inputs(paths: list[Path], repo_root: Path) -> list[InputFingerprint]:
    """Hash every file a verdict was derived from, deduped and ordered for stability."""
    seen: dict[str, str] = {}
    for path in paths:
        if not path.is_file():
            continue
        key = display_path(path, repo_root)
        if key in seen:
            continue
        try:
            seen[key] = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            continue
    return [InputFingerprint(path=key, sha256=seen[key]) for key in sorted(seen)]


def build_report(
    *,
    agent: str,
    workspace: str,
    repo_root: Path,
    candidate: CandidateConfig | None,
    findings: list[Finding],
    required_env_vars: list[RequiredEnvVar],
    inputs: list[InputFingerprint],
    discovered_at: datetime | None = None,
    last_validated_at: datetime | None = None,
) -> DiscoveryReport:
    now = discovered_at or datetime.now(UTC)
    return DiscoveryReport(
        agent=agent,
        workspace=workspace,
        repo_root=repo_root,
        harbor_version=harbor_version(),
        config_source=candidate.source if candidate is not None else None,
        findings=findings,
        required_env_vars=required_env_vars,
        inputs=inputs,
        discovered_at=now,
        last_validated_at=last_validated_at or now,
    )


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
        "last_validated_at": report.last_validated_at.isoformat(),
        "inputs_digest": report.inputs_digest,
        "inputs": [{"path": item.path, "sha256": item.sha256} for item in report.inputs],
    }


def _body(report: DiscoveryReport) -> list[str]:
    lines = [f"# Harbor eval setup for `{report.agent}`", ""]
    lines += _verdict_section(report)
    lines += _how_to_run_section(report)
    lines += _validation_section(report)
    lines += _env_section(report)
    lines += _repo_section(report)
    lines += _inputs_section(report)
    return lines


def _verdict_section(report: DiscoveryReport) -> list[str]:
    if report.runnable:
        source = report.config_source
        detail = source.detail if source is not None else "unknown"
        return [
            f"Harbor can run this repo's evals. The config in `{JOB_CONFIG_FILENAME}` was "
            f"{detail}, and every check below was answered by Harbor {report.harbor_version} "
            "rather than inferred.",
            "",
        ]

    lines = ["**Harbor cannot run this repo's evals yet.** Blocking:", ""]
    for finding in report.blocking:
        lines.append(f"- **{finding.name}** — {finding.message}")
        if finding.harbor_call:
            lines.append(f"  - reported by `{finding.harbor_call}`")
        if finding.hint:
            lines.append(f"  - {finding.hint}")
    lines.append("")
    if report.config_source is None:
        lines += [
            "No config could be assembled at all, so there is nothing to fix incrementally. "
            "Start with `harbor job init` and rerun discovery.",
            "",
        ]
    else:
        lines += [
            f"`{JOB_CONFIG_FILENAME}` is not part of this record: a config is only persisted "
            "once Harbor accepts its schema, so its absence means do not try to run one.",
            "",
        ]
    return lines


def _how_to_run_section(report: DiscoveryReport) -> list[str]:
    if not report.runnable:
        return []
    lines = [
        "## Running it",
        "",
        f"From `{report.repo_root}`, because the config uses repo-relative paths:",
        "",
        "```bash",
        f"harbor job start -c {JOB_CONFIG_FILENAME}",
        "```",
        "",
    ]
    if report.required_env_vars:
        names = " ".join(f"{item.name}=..." for item in report.required_env_vars)
        lines += [f"Set the host variables first: `{names}`", ""]
    lines += [
        "To confirm the tasks are solvable before trusting any agent's score, run Harbor's "
        "oracle, which replays each task's own solution and should score 1.0:",
        "",
        "```bash",
        f"harbor run -a oracle -c {JOB_CONFIG_FILENAME}",
        "```",
        "",
        "Discovery does not run this itself, because unlike every check above it builds and starts containers.",
        "",
    ]
    return lines


def _validation_section(report: DiscoveryReport) -> list[str]:
    rungs = [finding for finding in report.findings if finding.group == "validation"]
    if not rungs:
        return []
    lines = [
        "## What Harbor checked",
        "",
        "Each line is a Harbor call, so a failure here is the error a real run would hit.",
        "",
    ]
    for finding in rungs:
        lines.append(f"- `{_STATUS_MARK[finding.status]}` **{finding.name}**: {finding.message}")
        if finding.harbor_call:
            lines.append(f"  - via `{finding.harbor_call}`")
        if finding.hint:
            lines.append(f"  - {finding.hint}")
    lines.append("")
    return lines


def _env_section(report: DiscoveryReport) -> list[str]:
    if not report.required_env_vars:
        return ["## Host variables", "", "The config templates no host variables.", ""]
    lines = [
        "## Host variables",
        "",
        "Harbor resolves these from the environment at trial start and raises on a missing "
        "one. Whether this machine has them is a separate question, which `nemo eval-author "
        "doctor` answers.",
        "",
    ]
    for item in report.required_env_vars:
        default = f", default `{item.default}`" if item.default is not None else ", no default"
        lines.append(f"- `{item.name}`{default} — declared in `{display_path(item.declared_in, report.repo_root)}`")
    lines.append("")
    return lines


def _repo_section(report: DiscoveryReport) -> list[str]:
    probes = [finding for finding in report.findings if finding.group == "repo"]
    if not probes:
        return []
    lines = [
        "## Repo shape",
        "",
        "Context for authoring evals rather than running them, so nothing here blocks a run.",
        "",
    ]
    for finding in probes:
        lines.append(f"- `{_STATUS_MARK[finding.status]}` **{finding.name}**: {finding.message}")
    lines.append("")
    return lines


def _inputs_section(report: DiscoveryReport) -> list[str]:
    return [
        "## Freshness",
        "",
        f"Derived from {len(report.inputs)} file(s), digest `{report.inputs_digest}`. Rerun "
        "`nemo eval-author discover` to compare: an unchanged digest means these verdicts "
        "still hold and the ladder can be skipped.",
        "",
    ]


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


def canonical_digest(value: Any) -> str:
    """Hash a structure the way the rest of this plugin does, for cross-run comparison."""
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"
