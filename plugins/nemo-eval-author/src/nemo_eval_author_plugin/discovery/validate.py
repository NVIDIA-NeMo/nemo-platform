# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Run Harbor preflight checks against a repository-owned config."""

import contextlib
import shutil
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import Iterator
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path

from harbor.agents.factory import AgentFactory
from harbor.environments.factory import EnvironmentFactory
from harbor.job import Job
from harbor.models.agent.name import AgentName
from harbor.models.job.config import JobConfig
from harbor.models.task.config import TaskConfig
from harbor.models.task.paths import TaskPaths
from harbor.models.task.task import Task
from harbor.utils.env import get_required_host_vars
from harbor.utils.import_path import import_class
from nemo_eval_author_plugin.discovery.scan import ConfigCandidate
from nemo_insights_plugin.contracts.checks import CheckResult, CheckSeverity, CheckStatus
from pydantic import ValidationError


@dataclass
class RequiredEnvVar:
    """A host variable required by a Harbor config."""

    name: str
    default: str | None
    declared_in: Path


@dataclass
class ValidationOutcome:
    """Results from one Harbor preflight."""

    checks: list[CheckResult] = field(default_factory=list)
    required_env_vars: list[RequiredEnvVar] = field(default_factory=list)


def _check(
    name: str,
    status: CheckStatus,
    message: str,
    *,
    severity: CheckSeverity = "required",
    hint: str | None = None,
) -> CheckResult:
    return CheckResult(name=name, group="validation", status=status, severity=severity, message=message, hint=hint)


async def run_ladder(candidate: ConfigCandidate, repo_root: Path) -> ValidationOutcome:
    """Run the complete preflight without caching or skipping any check."""
    outcome = ValidationOutcome()
    with contextlib.chdir(repo_root):
        try:
            config = JobConfig.model_validate(candidate.data)
            config.validate_agent_concurrency_limits()
        except ValidationError as exc:
            errors = exc.errors(include_url=False, include_input=False)
            outcome.checks.append(_check("schema", "fail", f"Harbor rejected the job config: {errors}"))
            return outcome
        except ValueError as exc:
            outcome.checks.append(_check("schema", "fail", f"Harbor rejected the job config: {exc}"))
            return outcome
        outcome.checks.append(_check("schema", "pass", "Harbor accepts the job config schema."))

        job = await _resolve(config, outcome)
        _check_agent(config, outcome)
        _check_backend(config, outcome)
        outcome.checks.append(check_config_file(candidate.path, repo_root))
        if job is None:
            return outcome

        resolved = _resolved_task_paths(job)
        if resolved is None:
            outcome.checks.append(
                _check(
                    "compatibility",
                    "fail",
                    "This Harbor version does not expose Job._task_configs.",
                    hint="Install a Harbor version that exposes the resolved task list.",
                )
            )
            return outcome
        task_dirs = _check_tasks(resolved, outcome)
        _check_coverage(config, resolved, outcome)
        _check_required_env_vars(config, task_dirs, outcome)
    return outcome


async def _resolve(config: JobConfig, outcome: ValidationOutcome) -> Job | None:
    try:
        with tempfile.TemporaryDirectory(prefix="eval-author-jobs-") as scratch:
            job = await Job.create(config.model_copy(update={"jobs_dir": Path(scratch)}))
            job._close_logger_handlers()
    except Exception as exc:
        outcome.checks.append(
            _check(
                "resolution",
                "fail",
                f"Harbor could not resolve the job: {type(exc).__name__}: {exc}",
                hint="This error occurs before Harbor starts a container.",
            )
        )
        return None
    outcome.checks.append(_check("resolution", "pass", "Harbor resolved the job."))
    return job


def _resolved_task_paths(job: Job) -> list[Path] | None:
    task_configs = getattr(job, "_task_configs", None)
    if task_configs is None:
        return None
    paths: list[Path] = []
    for task_config in task_configs:
        try:
            paths.append(task_config.get_local_path().resolve())
        except ValueError:
            continue
    return paths


def _check_tasks(resolved: list[Path], outcome: ValidationOutcome) -> list[Path]:
    valid = [path for path in resolved if Task.is_valid_dir(path)]
    if not resolved:
        outcome.checks.append(_check("tasks", "fail", "The config resolves to zero tasks."))
        return []
    outcome.checks.append(
        _check(
            "tasks",
            "fail" if len(valid) != len(resolved) else "pass",
            f"{len(valid)} of {len(resolved)} task dirs are valid Harbor tasks.",
        )
    )
    return valid


def _check_coverage(config: JobConfig, resolved: list[Path], outcome: ValidationOutcome) -> None:
    resolved_set = {path.resolve() for path in resolved}
    dropped_any = False
    for dataset in config.datasets:
        if dataset.path is None or not dataset.path.is_dir():
            continue
        on_disk = [
            child
            for child in sorted(dataset.path.iterdir())
            if child.is_dir() and child.name != "task_template" and (child / "task.toml").is_file()
        ]
        dropped = [child for child in on_disk if child.resolve() not in resolved_set]
        if not dropped:
            continue
        dropped_any = True
        selected_dropped = [
            path
            for path in dropped
            if (not dataset.task_names or any(fnmatchcase(path.name, pattern) for pattern in dataset.task_names))
            and not any(fnmatchcase(path.name, pattern) for pattern in dataset.exclude_task_names or [])
        ]
        required = bool(selected_dropped) and dataset.n_tasks is None
        filtered = bool(dataset.task_names or dataset.exclude_task_names)
        reported = selected_dropped if required else dropped
        names = ", ".join(path.name for path in reported)
        outcome.checks.append(
            _check(
                "coverage",
                "fail" if required else "warn",
                f"Harbor did not resolve {len(reported)} task dirs: {names}.",
                severity="required" if required else "advisory",
                hint=(
                    "Harbor skipped a task selected by the dataset filters."
                    if required and filtered
                    else "Harbor skips these task dirs silently."
                    if required
                    else "The dataset filters or n_tasks select a task subset."
                ),
            )
        )
    if not dropped_any:
        outcome.checks.append(_check("coverage", "pass", "Harbor dropped no local task dirs."))


def _check_required_env_vars(config: JobConfig, task_dirs: list[Path], outcome: ValidationOutcome) -> None:
    required: dict[str, RequiredEnvVar] = {}

    def collect(env: dict[str, str], declared_in: Path) -> None:
        for name, default in get_required_host_vars(env):
            required.setdefault(name, RequiredEnvVar(name, default, declared_in))

    for task_dir in task_dirs:
        task_config = _task_config(task_dir)
        if task_config is None:
            continue
        path = TaskPaths(task_dir).config_path
        collect(task_config.environment.env, path)
        collect(task_config.verifier.env, path)
        collect(task_config.solution.env, path)
    collect(config.environment.env, Path("<job config>"))
    collect(config.verifier.env, Path("<job config>"))
    for agent in config.agents:
        collect(agent.env, Path("<job config>"))
    outcome.required_env_vars = sorted(required.values(), key=lambda item: item.name)
    names = ", ".join(item.name for item in outcome.required_env_vars)
    outcome.checks.append(
        _check("credentials", "pass", f"{len(required)} host variables required" + (f": {names}." if names else "."))
    )


def _task_config(task_dir: Path) -> TaskConfig | None:
    try:
        return TaskConfig.model_validate_toml(TaskPaths(task_dir).config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError, ValidationError):
        return None


def _check_agent(config: JobConfig, outcome: ValidationOutcome) -> None:
    for agent in config.agents:
        if agent.import_path is not None:
            with _evict_module_tree(agent.import_path):
                try:
                    imported = import_class(agent.import_path, label="agent")
                except (Exception, SystemExit) as exc:
                    outcome.checks.append(
                        _check("agent", "fail", f"Cannot import agent {agent.import_path}: {type(exc).__name__}: {exc}")
                    )
                else:
                    outcome.checks.append(_check("agent", "pass", f"Agent {imported.__name__} imports as a class."))
        elif agent.name is not None:
            try:
                AgentFactory.get_agent_class(AgentName(agent.name))
            except Exception as exc:
                outcome.checks.append(
                    _check("agent", "fail", f"Cannot load Harbor agent {agent.name}: {type(exc).__name__}: {exc}")
                )
            else:
                outcome.checks.append(_check("agent", "pass", f"Built-in agent {agent.name} is available."))


def _check_backend(config: JobConfig, outcome: ValidationOutcome) -> None:
    label = config.environment.import_path or (config.environment.type.value if config.environment.type else "docker")
    try:
        EnvironmentFactory.run_preflight(config.environment.type, config.environment.import_path)
    except (Exception, SystemExit) as exc:
        outcome.checks.append(
            _check("backend", "fail", f"Environment backend {label} is not ready: {type(exc).__name__}: {exc}")
        )
    else:
        outcome.checks.append(_check("backend", "pass", f"Environment backend {label} passed preflight."))


def check_config_file(config_path: Path, repo_root: Path) -> CheckResult:
    """Check the bytes that Harbor receives from its CLI."""
    harbor = _harbor_executable()
    if harbor is None:
        return _check(
            "round-trip",
            "warn",
            "The Harbor CLI round trip did not run.",
            severity="advisory",
            hint="No harbor executable exists on PATH.",
        )
    try:
        completed = subprocess.run(
            [harbor, "job", "start", "--print-config", "-c", str(config_path)],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return _check("round-trip", "warn", f"The Harbor CLI round trip failed: {exc}", severity="advisory")
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip().splitlines()
        return _check(
            "round-trip", "fail", f"The Harbor CLI rejected the config: {detail[-1] if detail else 'no output'}."
        )
    return _check("round-trip", "pass", "The config file loads through the Harbor CLI.")


def _harbor_executable() -> str | None:
    local = Path(sys.executable).parent / "harbor"
    return str(local) if local.is_file() else shutil.which("harbor")


@contextlib.contextmanager
def _evict_module_tree(import_path: str) -> Iterator[None]:
    """Import without cached modules from another repository."""
    module = import_path.split(":", 1)[0].split(".", 1)[0]
    previous = {
        name: cached for name, cached in list(sys.modules.items()) if name == module or name.startswith(f"{module}.")
    }
    for name in previous:
        sys.modules.pop(name)
    try:
        yield
    finally:
        for name in list(sys.modules):
            if name == module or name.startswith(f"{module}."):
                sys.modules.pop(name)
        sys.modules.update(previous)
