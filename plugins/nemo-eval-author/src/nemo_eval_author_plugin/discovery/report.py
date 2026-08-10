# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Discovery report contract and Markdown renderer."""

import shlex
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

import yaml
from nemo_eval_author_plugin.discovery.scan import RepositoryScan
from nemo_eval_author_plugin.discovery.validate import RequiredEnvVar, ValidationOutcome
from nemo_insights_plugin.contracts.checks import CheckResult, format_report, required_failures


@dataclass
class DiscoveryReport:
    """Repository facts and current Harbor preflight results."""

    agent: str
    workspace: str
    repo_root: Path
    config_path: Path | None
    dataset_paths: list[Path]
    ethos_path: str | None
    harbor_version: str
    required_env_vars: list[RequiredEnvVar]
    discovered_at: datetime
    fingerprint: str
    input_file_count: int
    checks: list[CheckResult]
    schema_version: int = field(init=False, default=1)

    @property
    def runnable(self) -> bool:
        """Return whether the repository-owned config passed all required checks."""
        return self.config_path is not None and not required_failures(self.checks)

    @property
    def run_command(self) -> str | None:
        """Return the Harbor command only for a runnable repository config."""
        if not self.runnable or self.config_path is None:
            return None
        config_path = self.config_path.resolve().relative_to(self.repo_root.resolve()).as_posix()
        cd_command = shlex.join(["cd", str(self.repo_root.resolve())])
        harbor_command = shlex.join(["harbor", "job", "start", "-c", config_path])
        return f"{cd_command} && {harbor_command}"


def harbor_version() -> str:
    """Return the installed Harbor version."""
    return version("harbor")


def build_report(
    *,
    agent: str,
    workspace: str,
    repo_root: Path,
    scan_result: RepositoryScan,
    validation: ValidationOutcome,
    trace_check: CheckResult,
    discovered_at: datetime | None = None,
) -> DiscoveryReport:
    """Build one report from the repository scan and current preflight."""
    return DiscoveryReport(
        agent=agent,
        workspace=workspace,
        repo_root=repo_root.resolve(),
        config_path=scan_result.config.path if scan_result.config else None,
        dataset_paths=scan_result.dataset_paths,
        ethos_path=scan_result.ethos_path,
        harbor_version=harbor_version(),
        required_env_vars=validation.required_env_vars,
        discovered_at=discovered_at or datetime.now(UTC),
        fingerprint=f"sha256:{scan_result.fingerprint}",
        input_file_count=scan_result.input_file_count,
        checks=[*scan_result.checks, *validation.checks, trace_check],
    )


def render_markdown(report: DiscoveryReport) -> str:
    """Render YAML front matter and a concise status report."""
    front = yaml.safe_dump(_front_matter(report), sort_keys=False, default_flow_style=False).rstrip()
    lines = [f"# Discovery report for `{report.agent}`"]
    status = format_report(report.checks)
    if status:
        lines.extend(["", "```text", status, "```"])
    if report.run_command:
        lines.extend(["", "## Run", "", "```bash", report.run_command, "```"])
    body = "\n".join(lines)
    return f"---\n{front}\n---\n\n{body}\n"


def _front_matter(report: DiscoveryReport) -> dict[str, Any]:
    return {
        "schema_version": report.schema_version,
        "agent": report.agent,
        "workspace": report.workspace,
        "repo_root": str(report.repo_root),
        "runnable": report.runnable,
        "config_path": _display_path(report.config_path, report.repo_root),
        "dataset_paths": [_display_path(path, report.repo_root) for path in report.dataset_paths],
        "run_command": report.run_command,
        "ethos_path": report.ethos_path,
        "harbor_version": report.harbor_version,
        "required_env_vars": [
            {
                "name": item.name,
                "default": item.default,
                "declared_in": _display_path(item.declared_in, report.repo_root),
            }
            for item in report.required_env_vars
        ],
        "discovered_at": report.discovered_at.isoformat(),
        "fingerprint": report.fingerprint,
        "input_file_count": report.input_file_count,
        "checks": [check.model_dump(mode="json") for check in report.checks],
    }


def _display_path(path: Path | None, repo_root: Path) -> str | None:
    if path is None:
        return None
    if not path.is_absolute():
        return path.as_posix()
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()
