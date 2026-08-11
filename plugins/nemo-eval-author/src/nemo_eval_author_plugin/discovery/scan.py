# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Scan repository-owned Harbor inputs."""

import hashlib
import json
import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from nemo_insights_plugin.contracts.checks import CheckResult, CheckSeverity, CheckStatus

_CONFIG_SUFFIXES = (".yaml", ".yml", ".json")
_MAX_CONFIG_DEPTH = 4
_PRUNE_DIR_NAMES = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".ruff_cache",
        ".pytest_cache",
        ".mypy_cache",
        ".tox",
        ".eggs",
        ".cache",
        "site-packages",
        "vendor",
        "cache",
        "dist",
        "build",
        "eval-and-optimize",
        ".nemo-optimizer",
        "jobs",
    }
)


@dataclass(frozen=True)
class ConfigCandidate:
    """A repository-owned Harbor config file."""

    path: Path
    data: dict[str, Any]

    @property
    def name(self) -> str:
        """Return the declared job name or the file name."""
        job_name = self.data.get("job_name")
        return job_name.strip() if isinstance(job_name, str) and job_name.strip() else self.path.name


@dataclass
class RepositoryScan:
    """The repository facts that the validation ladder needs."""

    configs: list[ConfigCandidate]
    dataset_paths: list[Path]
    ethos_path: str | None
    fingerprint: str
    input_file_count: int
    checks: list[CheckResult]


def _check(
    name: str,
    status: CheckStatus,
    message: str,
    *,
    severity: CheckSeverity = "required",
    hint: str | None = None,
) -> CheckResult:
    return CheckResult(name=name, group="repository", status=status, severity=severity, message=message, hint=hint)


def walk_dirs(root: Path, *, max_depth: int | None = None) -> Iterator[Path]:
    """Yield repository directories and skip generated trees."""
    for current, dir_names, _ in os.walk(root):
        directory = Path(current)
        depth = len(directory.relative_to(root).parts)
        dir_names[:] = sorted(
            name for name in dir_names if name not in _PRUNE_DIR_NAMES and (max_depth is None or depth < max_depth)
        )
        yield directory


def scan_repository(repo_root: Path, *, platform_ethos: tuple[str, bytes] | None = None) -> RepositoryScan:
    """Find repo-owned configs and local Harbor datasets."""
    repo_root = repo_root.resolve()
    configs = _config_candidates(repo_root)
    checks: list[CheckResult] = []
    if not configs:
        checks.append(
            _check(
                "config",
                "fail",
                "No repository-owned Harbor config file exists.",
                hint="Add a YAML, YML, or JSON config with a nonempty datasets or tasks list.",
            )
        )
    else:
        count = len(configs)
        checks.append(
            _check("config", "pass", f"Found {count} repository-owned Harbor config file{'s' if count != 1 else ''}.")
        )

    ethos = platform_ethos
    if ethos is None and (repo_root / "ETHOS.md").is_file():
        ethos = ("ETHOS.md", (repo_root / "ETHOS.md").read_bytes())
    if ethos is not None:
        checks.append(_check("ethos", "pass", f"{ethos[0]} defines the agent doctrine.", severity="advisory"))
    else:
        checks.append(
            _check(
                "ethos",
                "warn",
                "ETHOS.md does not exist at the repository root.",
                severity="advisory",
                hint="Add ETHOS.md to define the agent doctrine.",
            )
        )

    datasets = _dataset_paths(repo_root)
    fingerprint, count = _fingerprint(repo_root, [config.path for config in configs], ethos, datasets)
    return RepositoryScan(configs, datasets, ethos[0] if ethos else None, fingerprint, count, checks)


def _config_candidates(repo_root: Path) -> list[ConfigCandidate]:
    candidates: list[ConfigCandidate] = []
    for directory in walk_dirs(repo_root, max_depth=_MAX_CONFIG_DEPTH):
        for path in sorted(directory.iterdir()):
            if path.is_symlink() or not path.is_file() or path.suffix.lower() not in _CONFIG_SUFFIXES:
                continue
            data = _load_mapping(path)
            if data is not None and _has_work(data):
                candidates.append(ConfigCandidate(path=path, data=data))
    return sorted(
        candidates,
        key=lambda candidate: (
            len(candidate.path.relative_to(repo_root).parts) - 1,
            candidate.path.relative_to(repo_root).as_posix(),
        ),
    )


def _load_mapping(path: Path) -> dict[str, Any] | None:
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)
    except (OSError, UnicodeError, json.JSONDecodeError, yaml.YAMLError):
        return None
    return data if isinstance(data, dict) else None


def _has_work(data: dict[str, Any]) -> bool:
    return any(isinstance(data.get(name), list) and data[name] for name in ("datasets", "tasks"))


def _dataset_paths(repo_root: Path) -> list[Path]:
    datasets: set[Path] = set()
    for directory in walk_dirs(repo_root):
        if directory != repo_root and directory.name != "task_template" and (directory / "task.toml").is_file():
            datasets.add(directory.parent)
    return sorted(datasets)


def _fingerprint(
    repo_root: Path,
    config_paths: list[Path],
    ethos: tuple[str, bytes] | None,
    datasets: list[Path],
) -> tuple[str, int]:
    files = {path for path in [*config_paths, repo_root / "optimizer.yaml"] if path.is_file()}
    for dataset in datasets:
        if not dataset.is_relative_to(repo_root):
            continue
        for directory in walk_dirs(dataset):
            files.update(
                path for path in directory.iterdir() if path.is_file() and path.resolve().is_relative_to(repo_root)
            )
    files.discard(repo_root / "ETHOS.md")

    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(str(path.relative_to(repo_root)).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    if ethos is not None:
        digest.update(ethos[0].encode() + b"\0" + ethos[1] + b"\0")
    return digest.hexdigest(), len(files) + (ethos is not None)


async def probe_traces(client: Any, *, agent: str, workspace: str) -> CheckResult:
    """Check whether Intake has traces for later authoring steps."""
    try:
        page = await client.intake.spans.groups.list(
            workspace=workspace,
            by="session_id",
            page=1,
            page_size=1,
            filter={"agent_name": agent},
            sort="-span_count",
        )
    except Exception as exc:
        return _check(
            "traces",
            "warn",
            f"Cannot read traces for {agent}: {type(exc).__name__}: {exc}",
            severity="advisory",
        )
    total = page.pagination.total_results if page.pagination is not None else len(page.data)
    if not total:
        return _check("traces", "warn", f"No traces exist for {agent}.", severity="advisory")
    return _check("traces", "pass", f"{total} trace sessions exist for {agent}.", severity="advisory")
