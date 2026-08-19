# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared Harbor dataset, dependency, input, and result adapters."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import shlex
import shutil
import tempfile
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any, Protocol, TypeAlias, TypedDict
from uuid import uuid4

from harbor.constants import MAIN_SERVICE_NAME
from harbor.environments.base import BaseEnvironment
from harbor.environments.factory import EnvironmentFactory
from harbor.models.environment_type import EnvironmentType
from harbor.models.task.task import Task as HarborTaskModel
from harbor.models.trial.config import ServiceVolumeConfig
from harbor.models.trial.paths import EnvironmentPaths, TrialPaths
from nemo_experimentalist_plugin.entities import (
    Dataset,
    DatasetRef,
    DatasetValidationError,
    DataValue,
    DependencyCommandResult,
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
from nemo_experimentalist_plugin.experimentalist.components.evaluator.dataset_layout import (
    find_task_dirs,
    is_task_dir,
)


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
DEFAULT_TRACE_ARTIFACT_SOURCE = "/app/traces"
_ATIF_TRACE_SUFFIX = ".atif.json"
_SHELL_SYNTAX_TIMEOUT_SEC = 10.0
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

    def __init__(self, runtime: HarborDependencyRuntime, *, temp_root: Path | None = None) -> None:
        self._runtime = runtime
        self._temp_root = temp_root
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
        if self._temp_root is not None:
            self._temp_root.mkdir(parents=True, exist_ok=True)
        temp_dir = tempfile.TemporaryDirectory(prefix="nemo-harbor-deps-", dir=self._temp_root)
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

    async def execute(
        self,
        command: str,
        *,
        stdin: str | None = None,
        timeout: float = 30.0,
        cwd: str = "/app",
    ) -> DependencyCommandResult:
        """Execute a bounded command in the active Harbor task environment."""
        if self._environment is None:
            raise RuntimeError("Harbor dependency environment is not running")
        wrapped = command if stdin is None else f"printf %s {shlex.quote(stdin)} | (\n{command}\n)"
        result = await self._environment.exec(wrapped, cwd=cwd, timeout_sec=max(1, int(timeout)))
        return DependencyCommandResult(
            stdout=result.stdout or "",
            stderr=result.stderr or "",
            returncode=result.return_code,
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


def _trial_resources(
    trial_dir: Path, *, trace_format: str = "otlp"
) -> tuple[dict[str, ResourceRef], ResourceRef | None]:
    resources: dict[str, ResourceRef] = {
        "trial_dir": ResourceRef(
            uri=trial_dir.resolve().as_uri(),
            description=(
                "Harbor trial output directory for one task attempt. Contains config.json, result.json, "
                "trial.log, agent logs, verifier logs, and collected artifacts."
            ),
        )
    }
    otlp_trace_ref: ResourceRef | None = None
    atif_trace_ref: ResourceRef | None = None

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
            ref = ResourceRef(uri=uri, description=description, metadata={"trace_format": "otlp"})
            otlp_trace_ref = otlp_trace_ref or ref
            resources[f"trace:{trace_relative_path}"] = ref
        elif relative_path.endswith(_ATIF_TRACE_SUFFIX) and "traces" in Path(relative_path).parts[:-1]:
            trace_relative_path = relative_path.removeprefix("artifacts/")
            description = f"Agent execution ATIF trajectory for {trace_relative_path}."
            ref = ResourceRef(uri=uri, description=description, metadata={"trace_format": "atif"})
            atif_trace_ref = atif_trace_ref or ref
            resources[f"trace:{trace_relative_path}"] = ref
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

    selected = atif_trace_ref if trace_format == "atif" else otlp_trace_ref
    other = otlp_trace_ref if trace_format == "atif" else atif_trace_ref
    if selected is None and other is not None:
        found = "otlp" if trace_format == "atif" else "atif"
        logger.warning(
            f"Trial {trial_dir.name}: configured trace_format='{trace_format}' matched no trace "
            f"artifact, but {found} artifacts are present. This trial will have no trace — set "
            f"trace_format='{found}' if the agent under test emits {found.upper()}."
        )
    return resources, selected


class HarborJobOptions(Protocol):
    """The two fields any Harbor-backed evaluator config must supply to locate a run.

    Declared structurally so :func:`resolve_harbor_run_inputs` can serve both
    evaluator configs without importing either — the SDK-backed one lives in a
    module that already imports this one.
    """

    jobs_dir: Path
    job_name: str | None


@dataclass(frozen=True)
class HarborRunInputs:
    """Validated inputs both Harbor-backed evaluators resolve the same way.

    ``dataset`` is carried through already narrowed to :class:`HarborDataset` so
    callers need no second ``isinstance`` check to satisfy a type checker — the
    validation happened once, in :func:`resolve_harbor_run_inputs`.
    """

    dataset: HarborDataset
    dataset_path: Path
    agent_path: Path
    jobs_dir: Path
    job_name: str

    @property
    def job_dir(self) -> Path:
        """Directory Harbor writes this run's per-trial results into."""
        return self.jobs_dir / self.job_name


async def resolve_harbor_run_inputs(
    agent: Path,
    dataset: Dataset,
    options: HarborJobOptions,
    experiment_dir: Path | None,
) -> HarborRunInputs:
    """Validate an evaluation request and resolve the paths Harbor needs.

    The counterpart to :func:`trials_from_job_dir`: that one owns reading results
    back, this one owns getting in. Both evaluator types must agree on what "the
    same inputs" means — if one tightened its agent-path check or moved the
    verifier preflight, the A/B parity tests would still pass while the two
    silently diverged. Keeping the entry symmetric with the exit is what stops that.

    Verifier syntax is validated here, before any caller starts Docker: a typo in
    ``tests/test.sh`` is far cheaper to catch now than after an image build.

    Args:
        agent: Candidate directory to evaluate.
        dataset: Must be a :class:`HarborDataset` with a resolvable source.
        options: Evaluator options supplying ``jobs_dir`` and optional ``job_name``.
        experiment_dir: Experiment root that ``jobs_dir`` resolves against; the
            current working directory when ``None``.

    Returns:
        HarborRunInputs: Resolved dataset/agent paths and the run's job location.

    Raises:
        ValueError: If the dataset is not a Harbor dataset or has no source.
        FileNotFoundError: If the agent directory does not exist.
        DatasetValidationError: If a selected task's verifier fails preflight.
    """
    if not isinstance(dataset, HarborDataset):
        raise ValueError("Dataset must be a Harbor dataset")
    if dataset.source is None:
        raise ValueError("Harbor dataset source is required")

    agent_path = agent.expanduser().resolve()
    if not agent_path.is_dir():
        raise FileNotFoundError(f"Harbor agent path not found: {agent_path}")

    await dataset.validate()

    return HarborRunInputs(
        dataset=dataset,
        dataset_path=local_path_from_uri(dataset.source.uri, context="Harbor dataset reference").resolve(),
        agent_path=agent_path,
        jobs_dir=(experiment_dir or Path.cwd()) / options.jobs_dir,
        # Derived from the *resolved* directory, not the caller's spelling of it.
        # `job_name` is the cache identity, and the SDK's scoped agent import derives
        # its package name from the resolved dir too — the two must agree or a job dir
        # can be reused for a different agent (`--agent .` has an empty `.name`; a
        # symlink keeps its own name while resolving elsewhere).
        job_name=options.job_name or f"{agent_path.name}-{dataset.id}",
    )


def trials_from_job_dir(
    job_dir: Path,
    tasks: Sequence[Task],
    *,
    trace_format: str = "otlp",
) -> list[TrialResult]:
    """Adapt a finished Harbor job directory into evaluator-domain trial results.

    The job directory is the authoritative source for both Harbor-backed
    evaluators: it carries every verifier metric (not just the primary reward),
    the attempt index, the trial's error shape, and the on-disk trace and
    artifact references that the Analyzer and the Coder read. Whoever
    orchestrated the run — Harbor's ``Job`` directly or the SDK's
    ``HarborAgentTaskRunner`` — writes the same tree, so both evaluators share
    this adapter and produce equivalent :class:`TrialResult` objects.

    Args:
        job_dir: Harbor job directory holding one ``<trial>/result.json`` per attempt.
        tasks: Dataset tasks the run was asked to cover, used to resolve each
            trial back to its short Experimentalist task id and metric spec.
        trace_format: Trace artifact format selected as the trial's primary trace.

    Returns:
        list[TrialResult]: One result per trial directory that wrote a ``result.json``.

    Raises:
        FileNotFoundError: If the job directory does not exist. Returning no trials
            would be aggregated as an empty-but-valid result and read as a run that
            legitimately scored nothing, so an orchestrator that produced no job
            directory at all is surfaced instead of swallowed.
    """
    if not job_dir.is_dir():
        raise FileNotFoundError(
            f"Harbor job directory not found: {job_dir}. The run produced no results — "
            "check the orchestrator's logs for a job that failed before writing any trial."
        )

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
        # Prefer the dataset's own spec, but only when it points at a verifier;
        # a ref-less spec carries no more than the one derived from the trial dir.
        metric_spec = task.metric_specs.get("reward") if task is not None else None
        if metric_spec is None or metric_spec.ref is None:
            metric_spec = _trial_metric_spec(trial_dir, trial_data)

        exception_info = trial_data.get("exception_info")
        resources, trace = _trial_resources(trial_dir, trace_format=trace_format)

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
    def from_ref(cls, ref: DatasetRef, *, allow_empty: bool = False, **options: Any) -> HarborDataset:
        """Build a Harbor dataset from a local dataset reference."""
        dataset_path = local_path_from_uri(ref.uri, context="Harbor dataset reference")
        dataset_id = ref.metadata.get("id")
        if dataset_id is not None and not isinstance(dataset_id, str):
            raise ValueError("Harbor dataset ref metadata field 'id' must be a string")
        task_ids = cls._task_ids_from_metadata(ref.metadata.get("task_ids"))
        dataset = cls.from_path(
            dataset_path,
            dataset_id=dataset_id,
            allow_empty=allow_empty,
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
        allow_empty: bool = False,
        single_task: bool = False,
        **_ignored_options: Any,
    ) -> HarborDataset:
        """Build a Harbor dataset from a local Harbor task collection.

        A dataset holds task directories, which is the only shape Harbor's job
        config enumerates. ``single_task`` additionally reads *dataset_path*
        itself as one task — the shape of a task template, which is a task
        rather than a collection of them.
        """
        dataset_path = dataset_path.expanduser().resolve()
        if not dataset_path.exists():
            raise FileNotFoundError(f"Harbor dataset path not found: {dataset_path}")
        if not dataset_path.is_dir():
            raise ValueError(f"Harbor dataset path is not a directory: {dataset_path}")

        task_dirs = [dataset_path] if single_task and is_task_dir(dataset_path) else find_task_dirs(dataset_path)
        if not task_dirs and not allow_empty:
            detail = (
                " (it is itself a task directory; point the dataset at the directory holding it)"
                if is_task_dir(dataset_path)
                else ""
            )
            raise ValueError(f"Harbor dataset path contains no Harbor task directories: {dataset_path}{detail}")

        tasks = [cls._from_task_dir(task_dir) for task_dir in task_dirs]
        return cls(
            id=dataset_id or dataset_path.name,
            source=ResourceRef(
                uri=dataset_path.resolve().as_uri(),
                description="Harbor dataset root directory.",
            ),
            tasks=tasks,
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

    def add_tasks(self, tasks: list[Task]) -> None:
        """Copy Harbor task directories into this dataset and register them.

        The destination dataset owns independent copies, so an Insight-suite
        task can be evaluated through train or validation without depending on
        the suite's original directory.
        """
        if not tasks:
            return
        if self.source is None:
            raise ValueError(f"Harbor dataset {self.id!r} has no source directory")
        destination_root = local_path_from_uri(self.source.uri, context="Harbor dataset source").resolve()
        if not destination_root.is_dir():
            raise ValueError(f"Harbor dataset source is not a directory: {destination_root}")

        imported: dict[str, Task] = {}
        for task in tasks:
            if task.uri is None:
                raise ValueError(f"Harbor task {task.id!r} has no source directory")
            source_dir = local_path_from_uri(task.uri, context=f"Harbor task {task.id!r}").resolve()
            if not source_dir.is_dir() or not (source_dir / _HARBOR_CONFIG_FILENAME["name"]).is_file():
                raise ValueError(f"Harbor task {task.id!r} is not a task directory: {source_dir}")
            destination = destination_root / task.id
            staging = destination_root / f".{task.id}.staging-{uuid4().hex}"
            backup = destination_root / f".{task.id}.backup-{uuid4().hex}"
            shutil.copytree(source_dir, staging)
            try:
                self._from_task_dir(staging)
                if destination.exists():
                    logger.warning("Replacing existing Harbor task %s in dataset %s", task.id, self.id)
                    destination.rename(backup)
                staging.rename(destination)
                imported[task.id] = self._from_task_dir(destination)
            except BaseException:
                if destination.exists() and backup.exists():
                    shutil.rmtree(destination)
                if staging.exists():
                    shutil.rmtree(staging)
                if backup.exists() and not destination.exists():
                    backup.rename(destination)
                raise
            else:
                if backup.exists():
                    shutil.rmtree(backup)

        self.tasks = [imported.pop(task.id, task) for task in self.tasks]
        self.tasks.extend(imported.values())

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
