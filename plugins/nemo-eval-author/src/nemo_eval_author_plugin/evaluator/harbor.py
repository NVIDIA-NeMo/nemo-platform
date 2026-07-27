# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Harbor dataset adapter for evaluator-domain task objects."""

from __future__ import annotations

import asyncio
import hashlib
import importlib.machinery
import json
import logging
import os
import re
import shutil
import sys
import tempfile
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType, TracebackType
from typing import Any, TypeAlias, TypedDict
from uuid import uuid4

from harbor.constants import MAIN_SERVICE_NAME
from harbor.environments.base import BaseEnvironment
from harbor.environments.factory import EnvironmentFactory
from harbor.job import DatasetConfig, Job, JobConfig
from harbor.models.environment_type import EnvironmentType
from harbor.models.job.config import AgentConfig, ArtifactConfig, RetryConfig
from harbor.models.task.task import Task as HarborTaskModel
from harbor.models.trial.config import ServiceVolumeConfig
from harbor.models.trial.paths import EnvironmentPaths, TrialPaths
from nemo_eval_author_plugin.evaluator.base import (
    Evaluator,
    EvaluatorConfig,
    EvaluatorType,
)
from nemo_eval_author_plugin.evaluator.models import (
    Dataset,
    DatasetRef,
    DatasetValidationError,
    DataValue,
    DependencyRuntime,
    MetricResult,
    MetricSpec,
    ResourceRef,
    Task,
    TrialResult,
    local_path_from_uri,
    run_dependency_command,
    subset_dataset_id,
)
from pydantic import Field


class HarborResourceSpec(TypedDict):
    """Known Harbor task file or directory."""

    name: str
    description: str


TreeResourceSpec: TypeAlias = tuple[HarborResourceSpec, str, tuple[str, ...]]

_HARBOR_CONFIG_FILENAME: HarborResourceSpec = {
    "name": "task.toml",
    "description": "Harbor task configuration file.",
}
_INSTRUCTION_FILENAME: HarborResourceSpec = {
    "name": "instruction.md",
    "description": "Task instruction shown to the benchmark agent.",
}
_README_FILENAMES = ("README.md", "readme.md")
_ENVIRONMENT_DIRNAME: HarborResourceSpec = {
    "name": "environment",
    "description": (
        "Harbor task environment directory. Contains the container definition and supporting files Harbor uses "
        "to create the task environment, such as Dockerfile, docker-compose.yaml, singularity-compose.yaml, "
        "and dependency files."
    ),
}
_VERIFIER_DIRNAME: HarborResourceSpec = {
    "name": "tests",
    "description": (
        "Harbor verifier tests directory. Harbor copies this directory into the task environment at /tests "
        "after the agent phase, discovers test.{sh,ps1,cmd,bat}, and expects rewards under /logs/verifier "
        "as reward.txt or reward.json."
    ),
}
_ORACLE_DIRNAME: HarborResourceSpec = {
    "name": "solution",
    "description": (
        "Harbor oracle solution directory. Harbor's OracleAgent copies this directory into the task environment "
        "at /solution and discovers solve.{sh,ps1,cmd,bat} as the reference solution script."
    ),
}
_STEPS_DIRNAME: HarborResourceSpec = {
    "name": "steps",
    "description": (
        "Harbor multi-step task directory. Contains one subdirectory per [[steps]] entry; each step can provide "
        "instruction.md plus step-specific tests/ and solution/ directories that Harbor uses like the top-level "
        "verifier and oracle directories."
    ),
}
_TASK_TREE_RESOURCES: tuple[TreeResourceSpec, ...] = (
    (_ENVIRONMENT_DIRNAME, "environment_dir", ()),
    (_VERIFIER_DIRNAME, "verifier_dir", ("test",)),
    (_ORACLE_DIRNAME, "oracle_dir", ()),
    (_STEPS_DIRNAME, "steps_dir", ()),
)
_TRACE_ARTIFACT_SOURCE = "/app/traces"
_TRACE_ARTIFACT_DESTINATION = "traces"
_SHELL_SYNTAX_TIMEOUT_SEC = 10.0
_AGENT_IMPORT_ROOT = "_nemo_experimentalist_eval_agents"
_IDENTIFIER_RE = re.compile(r"\W+")
_TRIAL_LOG_DESCRIPTIONS = {
    "agent/oracle.txt": "Oracle-agent log captured when Harbor runs the reference solution.",
    "agent/setup/stdout.txt": "Agent setup stdout captured while Harbor uploads the agent and installs dependencies.",
    "exception.txt": "Exception traceback captured by Harbor for a failed trial.",
    "trial.log": "Harbor trial orchestration log covering environment setup, agent execution, verifier execution, artifact collection, and cleanup.",
    "verifier/reward.json": "Verifier reward JSON written under /logs/verifier. Harbor parses numeric entries from this file as trial metrics.",
    "verifier/reward.txt": "Verifier scalar reward file written under /logs/verifier. Harbor parses this file as the reward metric.",
    "verifier/test-stderr.txt": "Verifier stderr captured while Harbor runs the task tests from the /tests directory.",
    "verifier/test-stdout.txt": "Verifier stdout captured while Harbor runs the task tests from the /tests directory.",
}

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HarborVerifierValidationFailure:
    """Syntax failure found in one task's Harbor verifier."""

    task_id: str
    path: Path
    error: str
    line: int | None = None
    column: int | None = None


class HarborVerifierValidationError(DatasetValidationError):
    """Aggregated Harbor verifier syntax failures."""

    def __init__(self, failures: Sequence[HarborVerifierValidationFailure]) -> None:
        self.failures = tuple(failures)
        details = "\n".join(f"- {self._format_failure(failure)}" for failure in self.failures)
        super().__init__(f"Harbor verifier preflight validation failed:\n{details}")

    @staticmethod
    def _format_failure(failure: HarborVerifierValidationFailure) -> str:
        location = str(failure.path)
        if failure.line is not None:
            location = f"{location}:{failure.line}"
            if failure.column is not None:
                location = f"{location}:{failure.column}"
        return f"task {failure.task_id!r}: {location}: {failure.error}"


@dataclass(frozen=True)
class _VerifierSyntaxFailure:
    """Content-addressed verifier syntax failure."""

    error: str
    line: int | None = None
    column: int | None = None


class HarborEvaluatorConfig(EvaluatorConfig):
    """Configuration for Harbor evaluator."""

    job_name: str | None = Field(
        default=None, description="Name of the job to run. If not provided, a default name will be generated."
    )
    jobs_dir: Path = Field(
        default=Path("eval-and-optimize") / "results",
        description="Directory to store job results, resolved relative to the experiment directory.",
    )
    n_attempts: int = Field(default=1)
    n_concurrent_trials: int = Field(default=os.cpu_count() or 4)
    quiet: bool = Field(default=False)
    verifier_timeout_multiplier: float | None = Field(default=1.0)
    agent_timeout_multiplier: float | None = Field(default=1.0)
    agent_setup_timeout_multiplier: float | None = Field(default=1.0)
    environment_build_timeout_multiplier: float | None = Field(default=1.0)
    artifacts: list[str] = Field(default=[])
    retry: RetryConfig = Field(default=RetryConfig(exclude_exceptions=set()))
    import_path: str = Field(default="harbor_wrapper:WrappedAgent")
    trace_dir: str = Field(default=_TRACE_ARTIFACT_SOURCE)


class HarborDependencyRuntime(DependencyRuntime):
    """Harbor API-backed task environment runtime."""

    task_path: ResourceRef
    environment_type: str = "docker"
    force_build: bool = True
    delete: bool = True
    run_healthcheck: bool = True
    build_timeout_sec: int | None = None

    def context(self) -> HarborDependencyContext:
        """Return Harbor-specific dependency context."""
        return HarborDependencyContext(self)


class HarborDependencyContext:
    """Async context manager that starts and stops Harbor task dependencies."""

    def __init__(self, runtime: HarborDependencyRuntime) -> None:
        self._runtime = runtime
        self._environment: BaseEnvironment | None = None
        self._temp_dir: tempfile.TemporaryDirectory[str] | None = None

    async def __aenter__(self) -> DependencyRuntime:
        """Start Harbor dependencies and return the entered runtime."""
        try:
            await self._start_harbor_runtime()
            if self._runtime.readiness is not None:
                await run_dependency_command(self._runtime.readiness, "readiness")
        except BaseException:
            try:
                await self._stop_started_runtime()
            except Exception as stop_exc:
                logger.warning("Harbor dependency cleanup failed during startup error: %s", stop_exc)
            raise
        return self._runtime

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        """Stop Harbor dependencies after the wrapped block completes."""
        try:
            await self._stop_started_runtime()
        except Exception as stop_exc:
            if exc_type is None:
                raise
            logger.warning("Harbor dependency cleanup failed (original error suppressed): %s", stop_exc)
        return False

    async def _start_harbor_runtime(self) -> None:
        task_path = local_path_from_uri(self._runtime.task_path.uri, context="Harbor task reference").resolve()
        harbor_task = HarborTaskModel(task_path)
        context_id = uuid4()
        session_id = f"{harbor_task.short_name}__{context_id.hex[:12]}__env"
        temp_dir = tempfile.TemporaryDirectory(prefix="nemo-harbor-deps-")
        trial_paths = TrialPaths(Path(temp_dir.name))
        trial_paths.mkdir()

        env_paths = EnvironmentPaths.for_os(harbor_task.config.environment.os)
        main_artifacts_dir = trial_paths.host_artifact_path(MAIN_SERVICE_NAME, env_paths.artifacts_dir.as_posix())
        main_artifacts_dir.mkdir(parents=True, exist_ok=True)
        mounts = [
            ServiceVolumeConfig(
                type="bind",
                source=trial_paths.verifier_dir.resolve().absolute().as_posix(),
                target=str(env_paths.verifier_dir),
            ),
            ServiceVolumeConfig(
                type="bind",
                source=trial_paths.agent_dir.resolve().absolute().as_posix(),
                target=str(env_paths.agent_dir),
            ),
            ServiceVolumeConfig(
                type="bind",
                source=main_artifacts_dir.resolve().absolute().as_posix(),
                target=str(env_paths.artifacts_dir),
            ),
        ]
        if harbor_task.paths.tests_dir.is_dir():
            mounts.append(
                ServiceVolumeConfig(
                    type="bind",
                    source=harbor_task.paths.tests_dir.resolve().absolute().as_posix(),
                    target=str(env_paths.tests_dir),
                    read_only=True,
                )
            )
        environment = EnvironmentFactory.create_environment(
            EnvironmentType(self._runtime.environment_type),
            environment_dir=harbor_task.paths.environment_dir,
            environment_name=harbor_task.short_name,
            session_id=session_id,
            trial_paths=trial_paths,
            task_env_config=harbor_task.config.environment,
            mounts=mounts,
        )
        environment.context_id = context_id
        self._temp_dir = temp_dir
        self._environment = environment

        if environment.capabilities.mounted:
            trial_paths.chmod_dir()
            _chmod_path_chain(main_artifacts_dir, trial_paths.artifacts_dir)

        await asyncio.wait_for(
            environment.start(force_build=self._runtime.force_build),
            timeout=self._runtime.build_timeout_sec,
        )
        if self._runtime.run_healthcheck and harbor_task.config.environment.healthcheck is not None:
            await environment.run_healthcheck()

        self._runtime.metadata.update(
            {
                "harbor_task_path": str(task_path),
                "harbor_trial_dir": str(trial_paths.trial_dir),
                "harbor_environment_session_id": session_id,
            }
        )

    async def _stop_started_runtime(self) -> None:
        stop_error: Exception | None = None
        if self._environment is not None:
            try:
                await self._environment.stop(delete=self._runtime.delete)
            except Exception as exc:
                stop_error = exc
            finally:
                self._environment = None

        if self._runtime.stop is not None:
            try:
                await run_dependency_command(self._runtime.stop, "stop")
            except Exception as exc:
                if stop_error is None:
                    stop_error = exc

        if self._temp_dir is not None:
            self._temp_dir.cleanup()
            self._temp_dir = None
        if stop_error is not None:
            raise stop_error


def _chmod_path_chain(path: Path, stop_at: Path) -> None:
    current = path
    while True:
        current.chmod(0o777)
        if current == stop_at:
            break
        current = current.parent


HarborDataValue: TypeAlias = DataValue | ResourceRef


def _safe_identifier(value: str) -> str:
    identifier = _IDENTIFIER_RE.sub("_", value).strip("_")
    if not identifier:
        identifier = "path"
    if not identifier[0].isalpha() and identifier[0] != "_":
        identifier = f"_{identifier}"
    return identifier


def _agent_import_package(agent_path: Path) -> str:
    path_parts = [_safe_identifier(part) for part in agent_path.parts if part not in {"", agent_path.anchor}]
    tail = path_parts[-6:] or ["agent"]
    digest = hashlib.sha256(str(agent_path).encode("utf-8")).hexdigest()[:12]
    tail[-1] = f"{tail[-1]}_{digest}"
    return ".".join([_AGENT_IMPORT_ROOT, *tail])


def _ensure_package(name: str, search_path: Path | None = None) -> None:
    parts = name.split(".")
    for idx in range(1, len(parts) + 1):
        package_name = ".".join(parts[:idx])
        package = sys.modules.get(package_name)
        if package is None:
            package = ModuleType(package_name)
            package.__package__ = package_name
            package.__spec__ = importlib.machinery.ModuleSpec(package_name, loader=None, is_package=True)
            package.__path__ = []  # type: ignore[attr-defined]
            sys.modules[package_name] = package
            if idx > 1:
                parent_name = ".".join(parts[: idx - 1])
                setattr(sys.modules[parent_name], parts[idx - 1], package)
        if search_path is not None and idx == len(parts):
            package.__path__ = [str(search_path)]  # type: ignore[attr-defined]


def _scoped_import_path(agent_path: Path, import_path: str) -> tuple[str, str]:
    module_name, separator, attribute = import_path.partition(":")
    module_name = module_name.strip().lstrip(".")
    if not module_name:
        raise ValueError("import_path module is required")

    package_name = _agent_import_package(agent_path)
    _ensure_package(package_name, search_path=agent_path)
    scoped = f"{package_name}.{module_name}"
    if separator:
        scoped = f"{scoped}:{attribute}"
    return scoped, package_name


def _cleanup_scoped_imports(package_name: str) -> None:
    package = sys.modules.get(package_name)
    for module_name in list(sys.modules):
        if module_name == package_name or module_name.startswith(f"{package_name}."):
            sys.modules.pop(module_name, None)
    parent_name, _, child_name = package_name.rpartition(".")
    parent = sys.modules.get(parent_name)
    if parent is not None and getattr(parent, child_name, None) is package:
        delattr(parent, child_name)
    parts = package_name.split(".")
    for idx in range(len(parts) - 1, 0, -1):
        module_name = ".".join(parts[:idx])
        if any(name.startswith(f"{module_name}.") for name in sys.modules):
            break
        package = sys.modules.pop(module_name, None)
        parent_name, _, child_name = module_name.rpartition(".")
        parent = sys.modules.get(parent_name)
        if parent is not None and getattr(parent, child_name, None) is package:
            delattr(parent, child_name)


def _resolve_verifier_dir(task_dir: Path, config: dict[str, Any]) -> Path:
    verifier_config = config.get("verifier")
    if isinstance(verifier_config, dict):
        configured_dir = verifier_config.get("directory")
        if isinstance(configured_dir, str) and configured_dir.strip():
            path = Path(configured_dir).expanduser()
            return path if path.is_absolute() else task_dir / path

    for dirname in (_VERIFIER_DIRNAME["name"], "test"):
        verifier_dir = task_dir / dirname
        if verifier_dir.is_dir():
            return verifier_dir
    return task_dir / _VERIFIER_DIRNAME["name"]


def _python_syntax_failure(source: str, path: Path) -> _VerifierSyntaxFailure | None:
    try:
        compile(source, str(path), "exec")
    except SyntaxError as exc:
        return _VerifierSyntaxFailure(
            error=f"{type(exc).__name__}: {exc.msg}",
            line=exc.lineno,
            column=exc.offset,
        )
    except RecursionError as exc:
        return _VerifierSyntaxFailure(error=f"{type(exc).__name__}: {exc}")
    return None


async def _shell_syntax_failure(source: str) -> _VerifierSyntaxFailure | None:
    bash_path = shutil.which("bash", path=os.defpath)
    if bash_path is None:
        raise FileNotFoundError("bash executable not found on the system path")
    process = await asyncio.create_subprocess_exec(
        bash_path,
        "--noprofile",
        "--norc",
        "-n",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={"LC_ALL": "C", "PATH": os.defpath, "SHELLOPTS": "noexec"},
    )
    try:
        _, stderr = await asyncio.wait_for(
            process.communicate(source.encode("utf-8")),
            timeout=_SHELL_SYNTAX_TIMEOUT_SEC,
        )
    except (TimeoutError, asyncio.CancelledError):
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
        await process.communicate()
        raise
    if process.returncode == 0:
        return None

    error = stderr.decode("utf-8", errors="replace").strip() or f"bash -n exited with status {process.returncode}"
    line_match = re.search(r"\bline (\d+):", error)
    return _VerifierSyntaxFailure(
        error=error,
        line=int(line_match.group(1)) if line_match else None,
    )


def _harbor_metric_spec(ref: ResourceRef | None, task_name: str | None = None) -> MetricSpec:
    description = "Harbor verifier reward emitted for this task."
    if task_name:
        description = f"Harbor verifier reward emitted for {task_name}."
    return MetricSpec(name="reward", description=description, ref=ref)


def _trial_metric_spec(trial_dir: Path, trial_data: dict[str, Any]) -> MetricSpec:
    task_dir = _trial_task_path(trial_data)

    ref = None
    if task_dir is not None:
        for verifier_dirname in (_VERIFIER_DIRNAME["name"], "test"):
            verifier_dir = task_dir / verifier_dirname
            if verifier_dir.is_dir():
                ref = ResourceRef(
                    uri=verifier_dir.resolve().as_uri(),
                    description=_VERIFIER_DIRNAME["description"],
                )
                break
    if ref is None and (trial_dir / "verifier").is_dir():
        verifier_output_dir = trial_dir / "verifier"
        ref = ResourceRef(
            uri=verifier_output_dir.resolve().as_uri(),
            description=(
                "Harbor verifier output directory. In the task environment this is mounted at /logs/verifier "
                "and stores verifier logs and reward files."
            ),
        )

    task_name = trial_data.get("task_name")
    return _harbor_metric_spec(ref, task_name if isinstance(task_name, str) else None)


def _trial_task_path(trial_data: dict[str, Any]) -> Path | None:
    config = trial_data.get("config")
    if isinstance(config, dict):
        task_config = config.get("task")
        if isinstance(task_config, dict) and isinstance(task_config.get("path"), str):
            return Path(task_config["path"]).expanduser()

    task_ref = trial_data.get("task_id")
    if isinstance(task_ref, dict) and isinstance(task_ref.get("path"), str):
        return Path(task_ref["path"]).expanduser()
    return None


def _resolve_trial_task_id(
    trial_name: str,
    trial_data: dict[str, Any],
    task_map: dict[str, Task],
) -> str:
    task_path = _trial_task_path(trial_data)
    if task_path is not None:
        resolved_path = task_path.resolve()
        for task in task_map.values():
            if not task.uri:
                continue
            try:
                if local_path_from_uri(task.uri, context="Harbor task reference").resolve() == resolved_path:
                    return task.id
            except ValueError:
                continue
        if task_path.name in task_map:
            return task_path.name

    task_name = trial_data.get("task_name")
    if isinstance(task_name, str) and task_name:
        task_id = task_name.split("/")[-1]
    else:
        task_id = trial_name.rsplit("__", 1)[0]
    if task_id in task_map:
        return task_id

    trial_base = trial_name.rsplit("__", 1)[0]
    if trial_base in task_map:
        return trial_base

    return task_id


def _trial_attempt(trial_name: str) -> int | None:
    suffix = trial_name.rsplit("__", 1)[-1]
    if suffix.isdigit():
        return int(suffix)
    return None


def _is_trial_log_path(relative_path: str) -> bool:
    if relative_path in _TRIAL_LOG_DESCRIPTIONS:
        return True
    parts = relative_path.split("/")
    return len(parts) == 3 and parts[0] == "agent" and parts[1].startswith("command-") and parts[2] == "stdout.txt"


def _with_trace_artifact(artifacts: Sequence[str | ArtifactConfig], trace_source: str) -> list[str | ArtifactConfig]:
    for artifact in artifacts:
        if isinstance(artifact, ArtifactConfig):
            if artifact.source == trace_source or artifact.destination == _TRACE_ARTIFACT_DESTINATION:
                return list(artifacts)
        elif isinstance(artifact, str) and artifact in {trace_source, _TRACE_ARTIFACT_DESTINATION}:
            return list(artifacts)

    trace_artifact = ArtifactConfig(source=trace_source, destination=_TRACE_ARTIFACT_DESTINATION)
    return [trace_artifact, *artifacts]


def _trial_error(exception_info: Any) -> dict[str, DataValue] | None:
    if exception_info is None:
        return None
    if not isinstance(exception_info, dict):
        return {"exception_info": exception_info}

    error: dict[str, DataValue] = {}
    if "exception_type" in exception_info:
        error["type"] = exception_info["exception_type"]
    if "exception_message" in exception_info:
        error["message"] = exception_info["exception_message"]
    if "exception_traceback" in exception_info:
        error["traceback"] = exception_info["exception_traceback"]
    return error or {"exception_info": exception_info}


def _reward_values_from_file(path: Path) -> dict[str, Any]:
    if path.suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    return {"reward": path.read_text(encoding="utf-8").strip()}


def _trial_reward_values(trial_dir: Path, trial_data: dict[str, Any]) -> dict[str, Any]:
    verifier_result = trial_data.get("verifier_result")
    if isinstance(verifier_result, dict):
        rewards = verifier_result.get("rewards")
        if isinstance(rewards, dict):
            return rewards

    reward_paths = (
        trial_dir / "verifier" / "reward.json",
        trial_dir / "verifier" / "reward.txt",
        trial_dir / "reward.json",
        trial_dir / "reward.txt",
    )
    for path in reward_paths:
        if path.is_file():
            return _reward_values_from_file(path)
    return {}


def _trial_metrics(trial_dir: Path, trial_data: dict[str, Any], spec: MetricSpec) -> dict[str, MetricResult]:
    values = _trial_reward_values(trial_dir, trial_data)
    metrics: dict[str, MetricResult] = {}
    for name, value in values.items():
        try:
            metric_value = float(value)
        except (TypeError, ValueError):
            continue
        metrics[name] = MetricResult(name=name, value=metric_value, spec=spec)
    return metrics


def _trial_resources(trial_dir: Path) -> tuple[dict[str, ResourceRef], ResourceRef | None]:
    resources: dict[str, ResourceRef] = {
        "trial_dir": ResourceRef(
            uri=trial_dir.resolve().as_uri(),
            description=(
                "Harbor trial output directory for one task attempt. Contains config.json, result.json, "
                "trial.log, agent logs, verifier logs, and collected artifacts."
            ),
        )
    }
    trace_ref = None

    for path in sorted(candidate for candidate in trial_dir.rglob("*") if candidate.is_file()):
        relative_path = path.relative_to(trial_dir).as_posix()
        uri = path.resolve().as_uri()
        if relative_path == "config.json":
            resources["config"] = ResourceRef(
                uri=uri,
                description=(
                    "Harbor trial configuration snapshot. Records the task, agent, environment, verifier, "
                    "artifact collection, and job id used for this attempt."
                ),
            )
        elif relative_path == "result.json":
            resources["result"] = ResourceRef(
                uri=uri,
                description=(
                    "Harbor trial result JSON. Contains task and trial identifiers, agent info, verifier rewards, "
                    "exception info, phase timings, and token or cost usage."
                ),
            )
        elif path.suffix == ".jsonl" and "traces" in Path(relative_path).parts[:-1]:
            trace_relative_path = relative_path.removeprefix("artifacts/")
            description = f"Agent execution trace JSONL for {trace_relative_path}."
            trace_ref = trace_ref or ResourceRef(uri=uri, description=description)
            resources[f"trace:{trace_relative_path}"] = ResourceRef(uri=uri, description=description)
        elif _is_trial_log_path(relative_path):
            description = _TRIAL_LOG_DESCRIPTIONS.get(relative_path)
            if description is None and relative_path.startswith("agent/command-"):
                description = "Agent command stdout captured while Harbor runs the benchmark agent."
            description = description or f"Harbor trial log {relative_path}."
            resources[f"log:{relative_path}"] = ResourceRef(
                uri=uri,
                description=description,
            )
        elif relative_path.startswith("artifacts/"):
            artifact_relative_path = relative_path.removeprefix("artifacts/")
            description = f"Collected Harbor artifact {artifact_relative_path}."
            if artifact_relative_path == "manifest.json":
                description = (
                    "Harbor artifact manifest. Lists collected artifact files and the environment paths they were "
                    "copied from."
                )
            resources[f"artifact:{artifact_relative_path}"] = ResourceRef(
                uri=uri,
                description=description,
            )
        else:
            resources[f"artifact:{relative_path}"] = ResourceRef(
                uri=uri,
                description=f"Collected Harbor artifact {relative_path}.",
            )

    return resources, trace_ref


class HarborDataset(Dataset):
    """Harbor task collection mapped onto generic evaluator-domain objects.

    ## Navigating the dataset

    ``dataset.source.uri`` — ``file://`` URI of the dataset root.
    Iterate tasks with ``dataset.list_tasks()``.  Each ``Task`` exposes:

    - ``task.id``  — subdirectory name (e.g. ``"tau2-airline-13"``)
    - ``task.uri`` — ``file://`` URI of the task root directory

    Resolve a ``file://`` URI to a ``pathlib.Path``:

    .. code-block:: python

        from pathlib import Path
        from urllib.parse import unquote, urlparse

        task_dir = Path(unquote(urlparse(task.uri).path))
        dataset_root = Path(unquote(urlparse(dataset.source.uri).path))

    ## Task directory layout

    ::

        <task-id>/
          task.toml       # task config
          instruction.md  # agent prompt
          tests/
            test.sh       # verifier entry point (may be empty on live datasets)
          environment/    # container definition
          solution/       # optional oracle

    ## How to modify instructions

    Edit the ``instruction.md`` file in the task directory.

    ## How to modify the solution

    The entry point for the agent is the ``solve.sh`` script in the ``solution/`` directory.
    It is executed in the task environment and can modify it.

    The verifier script will run after the solve.sh script.

    ## How to add, remove, or modify a metric

    Metrics are defined by what ``tests/test.sh`` writes to ``/logs/verifier/``
    inside the container.  To change the metrics for a task, edit or replace
    that script.

    **How it runs:** after the agent finishes, Harbor copies ``tests/`` into the
    container at ``/tests`` and executes ``tests/test.sh``.  The script can read:

    - ``/logs/artifacts/traces/`` — **primary signal source**: OTLP trace files
      written by the agent as ``*.jsonl``.  Each line is an
      ``ExportTraceServiceRequest`` JSON object.  Spans live under
      ``resourceSpans[].scopeSpans[].spans[]``.  Span attributes are a list of
      ``{"key": str, "value": {"stringValue": str}}``.  Error spans carry
      ``error.type`` and ``error.message`` attributes.  Tool calls, LLM inputs/outputs,
      and execution results are all recorded here as structured spans — prefer this
      over raw log files for reliable, parseable signal.  Resolve the path via
      ``os.environ.get("TRACE_DIR", "/logs/artifacts/traces")`` so the script is
      testable locally.
    - ``/logs/agent/``    — raw agent process output (stdout/stderr, unstructured).
      Use only when the OTLP traces don't capture what you need.
    - ``/tests/``         — any helper files you place in ``tests/``

    and must write to:

    - ``/logs/verifier/reward.json`` — flat JSON object; **every value must be a
      plain number** (int or float).  Harbor calls ``float(value)`` on each entry
      and silently drops non-numeric values (nested objects, booleans, strings).

    Correct format::

        {"reward": 0.8, "my_metric": 1.0}

    **To add a new metric** — write it as an additional key in ``reward.json``::

        {"reward": 0.8, "my_metric": 1.0, "another_metric": 0.5}

    **To remove a metric** — omit its key from the JSON object.

    **To modify the scoring logic** — edit the ``test.sh`` script body.

    **Preferred pattern — separate script files**

    Write each metric as a standalone Python file in ``tests/`` (e.g.
    ``tests/check_my_metric.py``) and call it from ``test.sh``.  This avoids
    shell-escaping issues with heredocs and makes each script independently
    testable.

    ``tests/check_my_metric.py``:

    .. code-block:: python

        #!/usr/bin/env python3
        # Measures: <describe what this script measures>
        import json, pathlib, sys

        AGENT_DIR = pathlib.Path("/logs/agent")
        OUT = pathlib.Path("/logs/verifier/metric_my_metric.json")

        # Inspect AGENT_DIR for the behavior to measure.
        score = 1.0
        # ... compute score from files in AGENT_DIR ...

        OUT.write_text(json.dumps({"my_metric": score}))
        print(f"my_metric={score}", file=sys.stderr)  # captured in verifier stderr

    ``tests/test.sh``:

    .. code-block:: bash

        #!/usr/bin/env bash
        set -euo pipefail
        mkdir -p /logs/verifier
        SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

        # Run each metric script and collect its output.
        python3 "$SCRIPT_DIR/check_my_metric.py"

        # Merge all metric_*.json files into reward.json.
        python3 "$SCRIPT_DIR/merge_metrics.py"

    ``tests/merge_metrics.py`` (reusable across tasks):

    .. code-block:: python

        #!/usr/bin/env python3
        import json, glob, pathlib

        result = {}
        for f in sorted(glob.glob("/logs/verifier/metric_*.json")):
            result.update(json.load(open(f)))
        pathlib.Path("/logs/verifier/reward.json").write_text(json.dumps(result))

    **LLM judge — ``tests/check_judge.py``**:

    .. code-block:: python

        #!/usr/bin/env python3
        # Judge: scores agent response against the task instruction via LLM.
        import json, pathlib, sys, openai

        AGENT_DIR = pathlib.Path("/logs/agent")
        OUT = pathlib.Path("/logs/verifier/metric_judge.json")

        agent_log = AGENT_DIR / "agent_log.jsonl"
        turns = [json.loads(l) for l in agent_log.read_text().splitlines() if l.strip()]
        agent_response = next(
            (t["content"] for t in reversed(turns) if t.get("role") == "assistant"), ""
        )
        instruction = pathlib.Path("/tests/instruction.md").read_text()

        # OPENAI_API_KEY injected via task.toml [verifier] env = { OPENAI_API_KEY = "sk-..." }
        client = openai.OpenAI()
        verdict = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": (
                    "You are a strict evaluator. "
                    'Reply with JSON: {"score": <0.0-1.0>, "reason": "<one sentence>"}.'
                )},
                {"role": "user", "content": (
                    f"Instruction:\n{instruction}\n\nAgent response:\n{agent_response}\n\n"
                    "Score 1.0 if fully satisfied, 0.0 if not."
                )},
            ],
            response_format={"type": "json_object"},
        )
        result = json.loads(verdict.choices[0].message.content)
        score = float(result["score"])
        print(f"judge_score={score} reason={result.get('reason','')}", file=sys.stderr)
        OUT.write_text(json.dumps({"judge_score": score}))

    ``tests/test.sh`` calls it the same way as any other metric script::

        python3 "$SCRIPT_DIR/check_judge.py"
        python3 "$SCRIPT_DIR/merge_metrics.py"

    Live datasets ship with an empty ``test.sh`` — replace it entirely with the
    pattern above.

    ## Augmenting a dataset in place

    Edit task directories on disk — do **not** copy them elsewhere.

    .. code-block:: python

        for task in dataset.list_tasks():
            task_dir = Path(unquote(urlparse(task.uri).path))
            test_sh = task_dir / "tests" / "test.sh"
            test_sh.parent.mkdir(exist_ok=True)
            test_sh.write_text(check_script, encoding="utf-8")
            test_sh.chmod(0o755)
    """

    def __init__(
        self,
        id: str,
        source: ResourceRef | None = None,
        tasks: Sequence[Task] | None = None,
        metadata: dict[str, DataValue] | None = None,
    ) -> None:
        super().__init__(
            id=id,
            source=source,
            tasks=list(tasks or []),
            metadata=metadata or {},
        )

    @classmethod
    def from_ref(cls, ref: DatasetRef, **options: Any) -> HarborDataset:
        """Build a Harbor dataset from a local dataset reference."""
        dataset_path = local_path_from_uri(ref.uri, context="Harbor dataset reference")
        dataset_id = ref.metadata.get("id")
        if dataset_id is not None and not isinstance(dataset_id, str):
            raise ValueError("Harbor dataset ref metadata field 'id' must be a string")
        task_ids = cls._task_ids_from_metadata(ref.metadata.get("task_ids"))
        dataset = cls.from_path(
            dataset_path,
            dataset_id=dataset_id,
            **options,
        )
        return dataset.subset(task_ids) if task_ids is not None else dataset

    @staticmethod
    def _task_ids_from_metadata(value: DataValue) -> list[str] | None:
        """Validate an optional ordered task-id selection from DatasetRef metadata."""
        if value is None:
            return None
        if not isinstance(value, list) or not value:
            raise ValueError("Harbor dataset ref metadata field 'task_ids' must be a non-empty list of strings")
        if any(not isinstance(task_id, str) or not task_id for task_id in value):
            raise ValueError("Harbor dataset ref metadata field 'task_ids' must be a non-empty list of strings")
        if len(set(value)) != len(value):
            raise ValueError("Harbor dataset ref metadata field 'task_ids' must not contain duplicates")
        return value

    @classmethod
    def from_path(
        cls,
        dataset_path: Path,
        *,
        dataset_id: str | None = None,
        **_ignored_options: Any,
    ) -> HarborDataset:
        """Build a Harbor dataset from a local Harbor task collection."""
        dataset_path = dataset_path.expanduser().resolve()
        if not dataset_path.exists():
            raise FileNotFoundError(f"Harbor dataset path not found: {dataset_path}")
        if not dataset_path.is_dir():
            raise ValueError(f"Harbor dataset path is not a directory: {dataset_path}")

        task_dirs = cls._find_task_dirs(dataset_path)
        if not task_dirs:
            raise ValueError(f"Harbor dataset path contains no Harbor task directories: {dataset_path}")

        tasks = [cls._from_task_dir(task_dir) for task_dir in task_dirs]
        return cls(
            id=dataset_id or dataset_path.name,
            source=ResourceRef(
                uri=dataset_path.resolve().as_uri(),
                description="Harbor dataset root directory.",
            ),
            tasks=tasks,
        )

    @staticmethod
    def _find_task_dirs(dataset_path: Path) -> list[Path]:
        if dataset_path.is_dir() and (dataset_path / "task.toml").exists():
            return [dataset_path]
        return sorted(
            path
            for path in dataset_path.iterdir()
            if path.is_dir() and path.name != "task_template" and (path / "task.toml").exists()
        )

    @classmethod
    def _from_task_dir(cls, task_dir: Path) -> Task:
        config = tomllib.loads((task_dir / "task.toml").read_text(encoding="utf-8"))
        inputs: dict[str, HarborDataValue] = {}
        resources: dict[str, ResourceRef] = {}

        cls._add_instruction_inputs(task_dir, config, inputs, resources)
        if config:
            inputs["config"] = config

        cls._add_readme_inputs(task_dir, inputs, resources)
        cls._add_known_resources(task_dir, config, resources)

        return Task(
            uri=task_dir.resolve().as_uri(),
            description="Harbor task root directory.",
            id=task_dir.name,
            inputs=inputs,
            resources=resources,
            metric_specs=cls._task_metric_specs(task_dir, config),
            dependencies=cls._dependency_runtime(task_dir, config),
        )

    @classmethod
    def _add_instruction_inputs(
        cls,
        task_dir: Path,
        config: dict[str, Any],
        inputs: dict[str, HarborDataValue],
        resources: dict[str, ResourceRef],
    ) -> None:
        instruction_path = task_dir / _INSTRUCTION_FILENAME["name"]
        if instruction_path.exists():
            inputs["instruction"] = instruction_path.read_text(encoding="utf-8")
            resources["instruction"] = ResourceRef(
                uri=instruction_path.resolve().as_uri(),
                description=_INSTRUCTION_FILENAME["description"],
            )

        step_inputs = cls._step_inputs(task_dir, config, resources)
        if step_inputs:
            inputs["steps"] = step_inputs
            if "instruction" not in inputs:
                inputs["instruction"] = "\n\n---\n\n".join(
                    f"## Step {index + 1}: {step['name']}\n\n{step['instruction']}"
                    for index, step in enumerate(step_inputs)
                    if isinstance(step.get("instruction"), str)
                )

    @staticmethod
    def _step_inputs(
        task_dir: Path,
        config: dict[str, Any],
        resources: dict[str, ResourceRef],
    ) -> list[dict[str, Any]]:
        step_inputs: list[dict[str, Any]] = []
        steps_dir = task_dir / _STEPS_DIRNAME["name"]
        steps = config.get("steps")
        if not isinstance(steps, list):
            return step_inputs

        for index, step in enumerate(step for step in steps if isinstance(step, dict)):
            name = step.get("name")
            if not isinstance(name, str) or not name:
                continue
            instruction_path = steps_dir / name / _INSTRUCTION_FILENAME["name"]
            instruction = None
            if instruction_path.exists():
                instruction = instruction_path.read_text(encoding="utf-8").rstrip()
                resources[f"step_{index + 1}_instruction"] = ResourceRef(
                    uri=instruction_path.resolve().as_uri(),
                    description=f"Instruction for Harbor task step {name}.",
                )
            step_inputs.append(
                {
                    "name": name,
                    "instruction": instruction,
                    "config": step,
                }
            )
        return step_inputs

    @staticmethod
    def _add_readme_inputs(
        task_dir: Path,
        inputs: dict[str, HarborDataValue],
        resources: dict[str, ResourceRef],
    ) -> None:
        # Match against the directory listing rather than Path.exists(): on a
        # case-insensitive filesystem every candidate spelling "exists", which would
        # emit a URI whose casing does not match the file actually on disk.
        try:
            present = {entry.name for entry in task_dir.iterdir()}
        except OSError:
            return
        for name in _README_FILENAMES:
            if name not in present:
                continue
            ref = ResourceRef(
                uri=(task_dir / name).resolve().as_uri(),
                description="Task README.",
            )
            inputs["readme"] = ref
            resources["readme"] = ref
            return

    @staticmethod
    def _add_known_resources(
        task_dir: Path,
        config: dict[str, Any],
        resources: dict[str, ResourceRef],
    ) -> None:
        resources["task_dir"] = ResourceRef(
            uri=task_dir.resolve().as_uri(),
            description="Harbor task root directory.",
        )

        config_path = task_dir / _HARBOR_CONFIG_FILENAME["name"]
        if config_path.is_file():
            resources["task_config"] = ResourceRef(
                uri=config_path.resolve().as_uri(),
                description=_HARBOR_CONFIG_FILENAME["description"],
            )

        for spec, key, aliases in _TASK_TREE_RESOURCES:
            if key == "verifier_dir":
                verifier_dir = _resolve_verifier_dir(task_dir, config)
                if verifier_dir.is_dir():
                    resources[key] = ResourceRef(
                        uri=verifier_dir.resolve().as_uri(),
                        description=spec["description"],
                    )
                continue
            for name in (spec["name"], *aliases):
                path = task_dir / name
                if path.is_dir():
                    resources[key] = ResourceRef(
                        uri=path.resolve().as_uri(),
                        description=spec["description"],
                    )
                    break

    @staticmethod
    def _task_metric_specs(task_dir: Path, config: dict[str, Any]) -> dict[str, MetricSpec]:
        task_config = config.get("task")
        task_name = None
        if isinstance(task_config, dict) and isinstance(task_config.get("name"), str):
            task_name = task_config["name"]
        ref = None
        verifier_dir = _resolve_verifier_dir(task_dir, config)
        if verifier_dir.is_dir():
            ref = ResourceRef(
                uri=verifier_dir.resolve().as_uri(),
                description=_VERIFIER_DIRNAME["description"],
            )

        return {"reward": _harbor_metric_spec(ref, task_name)}

    @staticmethod
    def _dependency_runtime(task_dir: Path, config: dict[str, Any]) -> DependencyRuntime:
        environment_config = config.get("environment") if isinstance(config, dict) else None
        build_timeout = None
        if isinstance(environment_config, dict):
            raw_timeout = environment_config.get("build_timeout_sec")
            if isinstance(raw_timeout, int | float):
                build_timeout = int(raw_timeout)
        return HarborDependencyRuntime(
            task_path=ResourceRef(
                uri=task_dir.resolve().as_uri(),
                description="Harbor task directory to start via Harbor EnvironmentFactory.",
            ),
            force_build=True,
            build_timeout_sec=build_timeout,
        )

    def list_tasks(self) -> Sequence[Task]:
        """Return Harbor tasks."""
        return list(self.tasks)

    def get_task(self, task_id: str) -> Task:
        """Return a Harbor task by id."""
        for task in self.list_tasks():
            if task.id == task_id:
                return task
        raise ValueError(f"Task id not found in Harbor dataset {self.id!r}: {task_id}")

    async def validate(self) -> None:
        """Validate selected task verifier syntax without executing verifier code."""
        failures: list[HarborVerifierValidationFailure] = []
        cache: dict[tuple[str, str], _VerifierSyntaxFailure | None] = {}

        for task in self.list_tasks():
            if not task.uri:
                raise ValueError(f"Harbor task {task.id!r} URI is required for verifier validation")
            task_dir = local_path_from_uri(task.uri, context="Harbor task reference").resolve()
            config_path = task_dir / _HARBOR_CONFIG_FILENAME["name"]
            config = tomllib.loads(config_path.read_text(encoding="utf-8"))
            verifier_dir = _resolve_verifier_dir(task_dir, config)
            if not verifier_dir.is_dir():
                continue

            verifier_paths = sorted(path for path in verifier_dir.rglob("*.py") if path.is_file())
            shell_entrypoint = verifier_dir / "test.sh"
            if shell_entrypoint.is_file():
                verifier_paths.append(shell_entrypoint)

            for path in verifier_paths:
                source = path.read_text(encoding="utf-8")
                verifier_type = "shell" if path == shell_entrypoint else "python"
                cache_key = (verifier_type, hashlib.sha256(source.encode("utf-8")).hexdigest())
                syntax_failure = cache.get(cache_key)
                if cache_key not in cache:
                    if verifier_type == "shell":
                        syntax_failure = await _shell_syntax_failure(source)
                    else:
                        syntax_failure = _python_syntax_failure(source, path)
                    cache[cache_key] = syntax_failure

                if syntax_failure is not None:
                    failures.append(
                        HarborVerifierValidationFailure(
                            task_id=task.id,
                            path=path.resolve(),
                            error=syntax_failure.error,
                            line=syntax_failure.line,
                            column=syntax_failure.column,
                        )
                    )

        if failures:
            raise HarborVerifierValidationError(failures)

    def subset(self, task_ids: Sequence[str]) -> HarborDataset:
        """Return a Harbor dataset containing selected task ids."""
        selected_ids = set(task_ids)
        tasks = [task for task in self.list_tasks() if task.id in selected_ids]
        missing = selected_ids - {task.id for task in tasks}
        if missing:
            missing_text = ", ".join(sorted(missing))
            raise ValueError(f"Task id(s) not found in Harbor dataset {self.id!r}: {missing_text}")
        return HarborDataset(
            id=subset_dataset_id(self.id, [task.id for task in tasks]),
            source=self.source,
            tasks=tasks,
            metadata=dict(self.metadata),
        )


class HarborEvaluator(Evaluator):
    """Run Harbor evaluations and return parsed reward payloads."""

    evaluator_type: EvaluatorType = "harbor"

    def __init__(self, options: HarborEvaluatorConfig | None = None, experiment_dir: Path | None = None) -> None:
        super().__init__(options or HarborEvaluatorConfig(), experiment_dir=experiment_dir)

    async def _run(self, agent: Path, dataset: Dataset, options: HarborEvaluatorConfig) -> Sequence[TrialResult]:
        if not isinstance(dataset, HarborDataset):
            raise ValueError("Dataset must be a Harbor dataset")

        if dataset.source is None:
            raise ValueError("Harbor dataset source is required")
        dataset_path = local_path_from_uri(dataset.source.uri, context="Harbor dataset reference").resolve()

        options_dict = options.model_dump()
        experiment_dir = self.experiment_dir or Path.cwd()
        options_dict["jobs_dir"] = experiment_dir / options.jobs_dir
        options_dict["job_name"] = options.job_name or f"{agent.name}-{dataset.id}"
        import_path: str = options_dict.pop("import_path")
        trace_dir: str = options_dict.pop("trace_dir", _TRACE_ARTIFACT_SOURCE)
        options_dict["artifacts"] = _with_trace_artifact(options_dict.get("artifacts") or [], trace_dir)
        force_rerun: bool = options_dict.pop("force_rerun", False)

        agent_path = agent.expanduser().resolve()

        if not agent_path.is_dir():
            raise FileNotFoundError(f"Harbor agent path not found: {agent_path}")

        await dataset.validate()

        scoped_import_path, scoped_package = _scoped_import_path(agent_path, import_path)
        agents_config = [AgentConfig(import_path=scoped_import_path)]
        datasets_config = [DatasetConfig(path=dataset_path, task_names=[task.id for task in dataset.tasks])]
        job_config = JobConfig(**options_dict, agents=agents_config, datasets=datasets_config)
        if force_rerun:
            job_dir = job_config.jobs_dir / job_config.job_name
            if job_dir.exists():
                shutil.rmtree(job_dir)

        try:
            job = await Job.create(job_config)
            await job.run()
        finally:
            _cleanup_scoped_imports(scoped_package)

        trials = await self._trials_from_dir(job.job_dir, dataset.tasks)
        return trials

    async def _trials_from_dir(self, job_dir: Path, tasks: Sequence[Task]) -> Sequence[TrialResult]:
        task_map = {task.id: task for task in tasks}
        trials: list[TrialResult] = []
        for trial_dir in sorted(path for path in job_dir.iterdir() if path.is_dir()):
            result_path = trial_dir / "result.json"
            if not result_path.is_file():
                continue

            trial_data = json.loads(result_path.read_text(encoding="utf-8"))
            trial_id = trial_data.get("trial_name")
            if not isinstance(trial_id, str) or not trial_id:
                trial_id = trial_dir.name

            task_id = _resolve_trial_task_id(trial_id, trial_data, task_map)
            task = task_map.get(task_id)
            metric_spec = task.metric_specs["reward"] if task is not None and "reward" in task.metric_specs else None
            if metric_spec is not None and metric_spec.ref is None:
                metric_spec = None
            metric_spec = metric_spec or _trial_metric_spec(trial_dir, trial_data)

            exception_info = trial_data.get("exception_info")
            resources, trace = _trial_resources(trial_dir)

            trials.append(
                TrialResult(
                    id=trial_id,
                    task_id=task_id,
                    attempt=_trial_attempt(trial_id),
                    status="completed" if exception_info is None else "failed",
                    error=_trial_error(exception_info),
                    trace=trace,
                    outputs={},
                    resources=resources,
                    metrics=_trial_metrics(trial_dir, trial_data, metric_spec),
                )
            )
        return trials
