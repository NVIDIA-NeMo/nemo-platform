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
class ConfigReport:
    """Preflight results for one Harbor config."""

    name: str
    path: Path
    required_env_vars: list[RequiredEnvVar]
    checks: list[CheckResult]

    @property
    def runnable(self) -> bool:
        """Return whether the config passed all required checks."""
        return not required_failures(self.checks)


@dataclass
class DiscoveryReport:
    """Repository facts and current Harbor preflight results."""

    agent: str
    workspace: str
    repo_root: Path
    configs: list[ConfigReport]
    dataset_paths: list[Path]
    ethos_path: str | None
    harbor_version: str
    discovered_at: datetime
    fingerprint: str
    input_file_count: int
    repository_checks: list[CheckResult]
    trace_check: CheckResult
    schema_version: int = field(init=False, default=1)

    @property
    def runnable(self) -> bool:
        """Return whether all repository-owned configs passed required checks."""
        return bool(self.configs) and all(config.runnable for config in self.configs)

    @property
    def checks(self) -> list[CheckResult]:
        """Return repository, config, and trace checks in execution order."""
        checks = list(self.repository_checks)
        for config in self.configs:
            checks.extend(config.checks)
        checks.append(self.trace_check)
        return checks

    @property
    def run_command(self) -> str | None:
        """Return the Harbor command only for one runnable config."""
        if len(self.configs) != 1:
            return None
        return self.run_command_for(self.configs[0])

    def run_command_for(self, config: ConfigReport) -> str | None:
        """Return the Harbor command for one runnable config."""
        if not config.runnable:
            return None
        config_path = config.path.resolve().relative_to(self.repo_root.resolve()).as_posix()
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
    validations: list[ValidationOutcome],
    trace_check: CheckResult,
    discovered_at: datetime | None = None,
) -> DiscoveryReport:
    """Build one report from the repository scan and config preflights."""
    configs = [
        ConfigReport(
            name=candidate.name,
            path=candidate.path,
            required_env_vars=validation.required_env_vars,
            checks=validation.checks,
        )
        for candidate, validation in zip(scan_result.configs, validations, strict=True)
    ]
    return DiscoveryReport(
        agent=agent,
        workspace=workspace,
        repo_root=repo_root.resolve(),
        configs=configs,
        dataset_paths=scan_result.dataset_paths,
        ethos_path=scan_result.ethos_path,
        harbor_version=harbor_version(),
        discovered_at=discovered_at or datetime.now(UTC),
        fingerprint=f"sha256:{scan_result.fingerprint}",
        input_file_count=scan_result.input_file_count,
        repository_checks=scan_result.checks,
        trace_check=trace_check,
    )


def render_markdown(report: DiscoveryReport) -> str:
    """Render YAML front matter and a concise status report."""
    front = yaml.safe_dump(_front_matter(report), sort_keys=False, default_flow_style=False).rstrip()
    lines = [f"# Discovery report for `{report.agent}`"]
    status = format_report([*report.repository_checks, report.trace_check])
    if status:
        lines.extend(["", "```text", status, "```"])
    if report.configs:
        lines.extend(["", "## Harbor entrypoints"])
    for config in report.configs:
        path = _display_path(config.path, report.repo_root)
        lines.extend(
            [
                "",
                f"### `{config.name}` (`{path}`)",
                "",
                f"Runnable: {'true' if config.runnable else 'false'}",
                "",
                "```text",
                format_report(config.checks),
                "```",
            ]
        )
        if command := report.run_command_for(config):
            lines.extend(["", "```bash", command, "```"])
    body = "\n".join(lines)
    return f"---\n{front}\n---\n\n{body}\n"


def _front_matter(report: DiscoveryReport) -> dict[str, Any]:
    config = report.configs[0] if len(report.configs) == 1 else None
    return {
        "schema_version": report.schema_version,
        "agent": report.agent,
        "workspace": report.workspace,
        "repo_root": str(report.repo_root),
        "runnable": report.runnable,
        "configs": [
            {"name": config.name, "path": _display_path(config.path, report.repo_root)} for config in report.configs
        ],
        "config_path": _display_path(config.path if config is not None else None, report.repo_root),
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
            for config in report.configs
            for item in config.required_env_vars
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
