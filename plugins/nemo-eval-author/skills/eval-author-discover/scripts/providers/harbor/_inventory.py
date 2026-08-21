# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Find the Harbor artifacts a repository owns.

Standard library only, and safe to import when Harbor is absent, so an inventory
survives to orient in a repository the ladder cannot judge.

Everything is read from the local checkout: no client, no workspace, no trace
probe, and the agent doctrine comes from a local ``ETHOS.md``.

Everything here observes rather than proves. Finding a config file says nothing
about whether Harbor accepts it, which is why the ladder in ``_ladder.py`` runs
next whenever Harbor is importable.

``yaml`` is used when available and is not a dependency of this skill: Harbor
depends on PyYAML, so a repository with Harbor installed always has it. Without
it, config detection falls back to a top-level key scan and every candidate is
marked unparsed. A file PyYAML rejects falls back to that same scan, so a config
with broken syntax is reported rather than silently missing.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from _checks import ADVISORY, FAIL, PASS, WARN, CheckResult, check

try:
    import yaml
except ModuleNotFoundError:  # ships with Harbor; absent only when Harbor is
    yaml = None  # ty: ignore[invalid-assignment]

# Malformed YAML raises yaml.YAMLError, which is not a ValueError. Empty without
# PyYAML, so the except clause naming these stays valid either way.
_PARSE_ERRORS: tuple[type[BaseException], ...] = () if yaml is None else (yaml.YAMLError,)

_CONFIG_SUFFIXES = (".yaml", ".yml", ".json")
_MAX_CONFIG_DEPTH = 4
_WORK_KEYS = ("datasets", "tasks")
# Matches a top-level `datasets:` or `tasks:` key, for the no-PyYAML fallback.
_WORK_KEY_PATTERN = re.compile(r"^(?:{}):".format("|".join(_WORK_KEYS)), re.MULTILINE)
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
    """A repository-owned Harbor config file.

    ``data`` is empty when the file could not be parsed, either because PyYAML is
    absent or because the syntax is broken. The ladder needs parsed data, so an
    unparsed candidate is reported and skipped.
    """

    path: Path
    data: dict[str, Any]
    parsed: bool

    @property
    def name(self) -> str:
        """Return the declared job name or the file name."""
        job_name = self.data.get("job_name")
        return job_name.strip() if isinstance(job_name, str) and job_name.strip() else self.path.name


@dataclass
class RepositoryScan:
    """The repository facts the validation ladder needs."""

    configs: list[ConfigCandidate]
    dataset_paths: list[Path]
    task_paths: list[Path]
    ethos_path: str | None
    fingerprint: str
    input_file_count: int
    checks: list[CheckResult]


def _check(name: str, status: str, message: str, **kwargs: Any) -> CheckResult:
    return check(name, "repository", status, message, **kwargs)


def walk_dirs(root: Path, *, max_depth: int | None = None) -> Iterator[Path]:
    """Yield repository directories and skip generated trees."""
    for current, dir_names, _ in os.walk(root):
        directory = Path(current)
        depth = len(directory.relative_to(root).parts)
        dir_names[:] = sorted(
            name for name in dir_names if name not in _PRUNE_DIR_NAMES and (max_depth is None or depth < max_depth)
        )
        yield directory


def scan_repository(repo_root: Path) -> RepositoryScan:
    """Find repo-owned configs, Harbor datasets, and task directories."""
    repo_root = repo_root.resolve()
    configs = _config_candidates(repo_root)
    checks: list[CheckResult] = []

    if not configs:
        checks.append(
            _check(
                "config",
                FAIL,
                "No repository-owned Harbor config file exists.",
                hint="Add a YAML, YML, or JSON config with a nonempty datasets or tasks list.",
            )
        )
    else:
        count = len(configs)
        plural = "s" if count != 1 else ""
        checks.append(_check("config", PASS, "Found {} repository-owned Harbor config file{}.".format(count, plural)))

    unparsed = [candidate for candidate in configs if not candidate.parsed]
    if unparsed:
        names = ", ".join(candidate.path.name for candidate in unparsed)
        checks.append(
            _check(
                "config-parse",
                FAIL,
                "Cannot read {} config file{}: {}.".format(len(unparsed), "s" if len(unparsed) != 1 else "", names),
                hint=(
                    "Install PyYAML, which arrives with Harbor, to read YAML configs."
                    if yaml is None
                    else "Fix the YAML syntax in each file this message names."
                ),
            )
        )

    ethos: tuple[str, bytes] | None = None
    ethos_file = repo_root / "ETHOS.md"
    if ethos_file.is_file():
        try:
            ethos = ("ETHOS.md", ethos_file.read_bytes())
        except OSError as exc:
            checks.append(
                _check(
                    "ethos",
                    WARN,
                    "ETHOS.md exists but cannot be read: {}.".format(exc.strerror or exc),
                    severity=ADVISORY,
                    hint="Make ETHOS.md readable to record the agent doctrine.",
                )
            )
        else:
            checks.append(_check("ethos", PASS, "ETHOS.md defines the agent doctrine.", severity=ADVISORY))
    else:
        checks.append(
            _check(
                "ethos",
                WARN,
                "ETHOS.md does not exist at the repository root.",
                severity=ADVISORY,
                hint="Add ETHOS.md to define the agent doctrine.",
            )
        )

    tasks = _task_paths(repo_root)
    datasets = _dataset_paths(tasks)
    if tasks:
        checks.append(
            _check(
                "tasks-on-disk",
                PASS,
                "Found {} task {} in {} dataset {}.".format(
                    len(tasks),
                    "directory" if len(tasks) == 1 else "directories",
                    len(datasets),
                    "directory" if len(datasets) == 1 else "directories",
                ),
                severity=ADVISORY,
                proven=False,
            )
        )
    else:
        checks.append(
            _check(
                "tasks-on-disk",
                WARN,
                "No task directories exist. A Harbor task directory holds a task.toml.",
                severity=ADVISORY,
                proven=False,
            )
        )

    fingerprint, count = _fingerprint(repo_root, [config.path for config in configs], ethos, datasets)
    return RepositoryScan(
        configs=configs,
        dataset_paths=datasets,
        task_paths=tasks,
        ethos_path=ethos[0] if ethos else None,
        fingerprint=fingerprint,
        input_file_count=count,
        checks=checks,
    )


def _config_candidates(repo_root: Path) -> list[ConfigCandidate]:
    candidates: list[ConfigCandidate] = []
    for directory in walk_dirs(repo_root, max_depth=_MAX_CONFIG_DEPTH):
        for path in sorted(directory.iterdir()):
            if path.is_symlink() or not path.is_file() or path.suffix.lower() not in _CONFIG_SUFFIXES:
                continue
            candidate = _candidate(path)
            if candidate is not None:
                candidates.append(candidate)
    return sorted(
        candidates,
        key=lambda candidate: (
            len(candidate.path.relative_to(repo_root).parts) - 1,
            candidate.path.relative_to(repo_root).as_posix(),
        ),
    )


def _candidate(path: Path) -> ConfigCandidate | None:
    """Return a candidate when the file declares Harbor work, else None."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None

    is_json = path.suffix.lower() == ".json"
    if is_json or yaml is not None:
        try:
            data = json.loads(text) if is_json else yaml.safe_load(text)
        except (json.JSONDecodeError, ValueError, *_PARSE_ERRORS):
            pass  # unparseable, so fall back to the key scan
        else:
            if not isinstance(data, dict) or not _has_work(data):
                return None
            return ConfigCandidate(path=path, data=data, parsed=True)

    if not _WORK_KEY_PATTERN.search(text):
        return None
    return ConfigCandidate(path=path, data={}, parsed=False)


def _has_work(data: dict[str, Any]) -> bool:
    return any(isinstance(data.get(name), list) and data[name] for name in _WORK_KEYS)


def _task_paths(repo_root: Path) -> list[Path]:
    return sorted(
        directory
        for directory in walk_dirs(repo_root)
        if directory != repo_root and directory.name != "task_template" and (directory / "task.toml").is_file()
    )


def _dataset_paths(tasks: list[Path]) -> list[Path]:
    """Return the directories holding the tasks, which is what Harbor calls a dataset."""
    return sorted({task.parent for task in tasks})


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
            try:
                entries = list(directory.iterdir())
            except OSError:
                continue
            files.update(path for path in entries if path.is_file() and path.resolve().is_relative_to(repo_root))
    files.discard(repo_root / "ETHOS.md")

    digest = hashlib.sha256()
    counted = 0
    for path in sorted(files):
        body = _file_digest(path)
        if body is None:
            continue
        digest.update(str(path.relative_to(repo_root)).encode())
        digest.update(b"\0")
        digest.update(body)
        digest.update(b"\0")
        counted += 1
    if ethos is not None:
        digest.update(ethos[0].encode() + b"\0" + ethos[1] + b"\0")
    return digest.hexdigest(), counted + (ethos is not None)


def _file_digest(path: Path) -> bytes | None:
    """Return the file's digest, or None when it cannot be read.

    Hashing each file separately keeps a file the fingerprint cannot read out of
    the digest entirely, rather than contributing the bytes read before the
    failure. ``file_digest`` reads in chunks, so a large repository-owned dataset
    never lands in memory whole.
    """
    try:
        with path.open("rb") as source:
            return hashlib.file_digest(source, "sha256").digest()
    except OSError:
        return None
