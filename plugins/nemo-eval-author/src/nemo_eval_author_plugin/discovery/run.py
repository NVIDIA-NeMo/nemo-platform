# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Orchestration for ``nemo agents eval-author discover``."""

import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from nemo_eval_author_plugin.discovery import report, scan, validate
from nemo_experimentalist_plugin.client import make_client
from nemo_platform import AsyncNeMoPlatform
from nemo_platform.config.config import Config

FILESET_NAME = "nemo-eval-author"
REPORT_FILENAME = "discovery.md"
_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


@dataclass
class DiscoverOptions:
    """Resolved command options."""

    repo_root: Path
    agent: str | None = None
    dry_run: bool = False


@dataclass
class DiscoverResult:
    """The report and upload result for one invocation."""

    report: report.DiscoveryReport
    markdown: str
    uploaded: bool = False
    dry_run: bool = False
    upload_error: str | None = None

    @property
    def ok(self) -> bool:
        """Return the command exit condition."""
        return self.report.runnable and (self.dry_run or self.uploaded)


async def discover(options: DiscoverOptions) -> DiscoverResult:
    """Scan, revalidate, report, and optionally upload one repository."""
    repo_root = options.repo_root.resolve()
    agent = _slug(options.agent) if options.agent is not None else _infer_agent_name(repo_root)
    workspace = _active_workspace()
    client = make_client(None)
    try:
        return await _discover(client, options, repo_root=repo_root, agent=agent, workspace=workspace)
    finally:
        await client.close()


async def _discover(
    client: AsyncNeMoPlatform,
    options: DiscoverOptions,
    *,
    repo_root: Path,
    agent: str,
    workspace: str,
) -> DiscoverResult:
    scan_result = scan.scan_repository(repo_root)
    validation = validate.ValidationOutcome()
    if scan_result.config is not None:
        validation = await validate.run_ladder(scan_result.config, repo_root)
    trace_check = await scan.probe_traces(client, agent=agent, workspace=workspace)
    record = report.build_report(
        agent=agent,
        workspace=workspace,
        repo_root=repo_root,
        scan_result=scan_result,
        validation=validation,
        trace_check=trace_check,
    )
    markdown = report.render_markdown(record)
    result = DiscoverResult(report=record, markdown=markdown, dry_run=options.dry_run)
    if options.dry_run:
        return result

    try:
        await client.files.upload_content(
            content=markdown.encode("utf-8"),
            remote_path=f"{agent}/{REPORT_FILENAME}",
            fileset=FILESET_NAME,
            workspace=workspace,
            fileset_auto_create=True,
        )
    except Exception as exc:
        result.upload_error = f"{type(exc).__name__}: {exc}"
    else:
        result.uploaded = True
    return result


def _active_workspace() -> str:
    return Config.load().resolve().workspace


def _infer_agent_name(repo_root: Path) -> str:
    """Read a root profile name, or use the repository directory."""
    try:
        data = yaml.safe_load((repo_root / "optimizer.yaml").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError):
        data = None
    declared = data.get("agent") if isinstance(data, dict) else None
    return _slug(declared) if isinstance(declared, str) and declared.strip() else _slug(repo_root.name)


def _slug(value: str) -> str:
    slug = _SLUG_PATTERN.sub("-", value.strip().lower()).strip("-")
    return slug or "agent"


__all__ = ["DiscoverOptions", "DiscoverResult", "discover"]
