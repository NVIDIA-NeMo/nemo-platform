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

_CONFIG_DIRS = ("configs", ".", "harbor", ".harbor", "evals")
_CONFIG_SUFFIXES = (".yaml", ".yml", ".json")
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
    }
)


@dataclass(frozen=True)
class ConfigCandidate:
    """A repository-owned Harbor config file."""

    path: Path
    data: dict[str, Any]


@dataclass
class RepositoryScan:
    """The repository facts that the validation ladder needs."""

    config: ConfigCandidate | None
    dataset_paths: list[Path]
    ethos_path: Path | None
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


def walk_dirs(root: Path) -> Iterator[Path]:
    """Yield repository directories and skip generated trees."""
    for current, dir_names, _ in os.walk(root):
        dir_names[:] = sorted(name for name in dir_names if name not in _PRUNE_DIR_NAMES)
        yield Path(current)


def scan_repository(repo_root: Path) -> RepositoryScan:
    """Find one repo-owned config and local Harbor datasets."""
    repo_root = repo_root.resolve()
    candidates = _config_candidates(repo_root)
    checks: list[CheckResult] = []
    config = candidates[0] if candidates else None
    if config is None:
        checks.append(
            _check(
                "config",
                "fail",
                "No repository-owned Harbor config file exists.",
                hint="Add a YAML, YML, or JSON config with a nonempty datasets or tasks list.",
            )
        )
    else:
        checks.append(_check("config", "pass", f"Using Harbor config {config.path.relative_to(repo_root)}."))
    if len(candidates) > 1:
        extras = ", ".join(str(item.path.relative_to(repo_root)) for item in candidates[1:])
        checks.append(
            _check(
                "config",
                "warn",
                f"More Harbor config files exist: {extras}.",
                severity="advisory",
                hint="Discovery uses the first file in its fixed search order.",
            )
        )

    ethos_path = repo_root / "ETHOS.md"
    if ethos_path.is_file():
        checks.append(_check("ethos", "pass", "ETHOS.md defines the agent doctrine.", severity="advisory"))
    else:
        ethos_path = None
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
    fingerprint, count = _fingerprint(repo_root, config.path if config else None, ethos_path, datasets)
    return RepositoryScan(config, datasets, ethos_path, fingerprint, count, checks)


def _config_candidates(repo_root: Path) -> list[ConfigCandidate]:
    candidates: list[ConfigCandidate] = []
    for relative in _CONFIG_DIRS:
        directory = repo_root if relative == "." else repo_root / relative
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir()):
            if not path.is_file() or path.suffix.lower() not in _CONFIG_SUFFIXES:
                continue
            try:
                if not path.resolve().is_relative_to(repo_root):
                    continue
            except (OSError, RuntimeError):
                continue
            data = _load_mapping(path)
            if data is not None and _has_work(data):
                candidates.append(ConfigCandidate(path=path, data=data))
    return candidates


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
    config_path: Path | None,
    ethos_path: Path | None,
    datasets: list[Path],
) -> tuple[str, int]:
    files: set[Path] = {
        path for path in (config_path, ethos_path, repo_root / "optimizer.yaml") if path and path.is_file()
    }
    for dataset in datasets:
        if not dataset.is_relative_to(repo_root):
            continue
        for directory in walk_dirs(dataset):
            files.update(path for path in directory.iterdir() if path.is_file())

    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(str(path.relative_to(repo_root)).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest(), len(files)


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
