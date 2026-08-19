# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Direct Harbor evaluator orchestration."""

import hashlib
import importlib.machinery
import os
import re
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType
from typing import Literal

from harbor.job import DatasetConfig, Job, JobConfig
from harbor.models.job.config import AgentConfig, ArtifactConfig, RetryConfig, VerifierConfig
from nemo_experimentalist_plugin.entities import Dataset, Task, TrialResult
from nemo_experimentalist_plugin.experimentalist import roles
from nemo_experimentalist_plugin.experimentalist.components.evaluator.base import (
    EvaluatorConfig,
    EvaluatorType,
)
from nemo_experimentalist_plugin.experimentalist.components.evaluator.entrypoint import (
    DEFAULT_AGENT_IMPORT_PATH,
    split_import_path,
)
from nemo_experimentalist_plugin.experimentalist.components.evaluator.harbor import (
    DEFAULT_TRACE_ARTIFACT_SOURCE,
    HarborDataset,
    resolve_harbor_run_inputs,
    trials_from_job_dir,
)
from pydantic import Field

_TRACE_ARTIFACT_DESTINATION = "traces"
_AGENT_IMPORT_ROOT = "_nemo_experimentalist_eval_agents"
_IDENTIFIER_RE = re.compile(r"\W+")


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
    module_name, attribute = split_import_path(import_path)

    package_name = _agent_import_package(agent_path)
    _ensure_package(package_name, search_path=agent_path)
    scoped = f"{package_name}.{module_name}"
    return f"{scoped}:{attribute}", package_name


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


def _validated_job_dir(jobs_dir: Path, job_name: str) -> Path:
    """Resolve ``jobs_dir / job_name`` and require it stay under ``jobs_dir``."""
    resolved_jobs_dir = jobs_dir.resolve()
    candidate = (jobs_dir / job_name).resolve()
    if candidate == resolved_jobs_dir or not candidate.is_relative_to(resolved_jobs_dir):
        raise ValueError(
            f"Resolved job directory {candidate} is not a strict descendant of "
            f"{resolved_jobs_dir} (job_name={job_name!r})"
        )
    return candidate


def _with_trace_artifact(artifacts: Sequence[str | ArtifactConfig], trace_source: str) -> list[str | ArtifactConfig]:
    for artifact in artifacts:
        if isinstance(artifact, ArtifactConfig):
            if artifact.source == trace_source or artifact.destination == _TRACE_ARTIFACT_DESTINATION:
                return list(artifacts)
        elif isinstance(artifact, str) and artifact in {trace_source, _TRACE_ARTIFACT_DESTINATION}:
            return list(artifacts)

    trace_artifact = ArtifactConfig(source=trace_source, destination=_TRACE_ARTIFACT_DESTINATION)
    return [trace_artifact, *artifacts]


class HarborEvaluatorConfig(EvaluatorConfig):
    """Configuration for direct Harbor evaluation."""

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
    import_path: str = Field(default=DEFAULT_AGENT_IMPORT_PATH)
    trace_dir: str = Field(default=DEFAULT_TRACE_ARTIFACT_SOURCE)
    trace_format: Literal["otlp", "atif"] = Field(
        default="otlp",
        description=(
            "Which trace artifact becomes the trial's trace. Both are still collected and "
            "exposed in resources; this only selects the one that gets uploaded and analysed."
        ),
    )


class HarborNativeOutcomeEvaluator(roles.OutcomeEvaluator):
    """Run Harbor evaluations directly and return parsed reward payloads."""

    name = "harbor-native"
    dataset_type = HarborDataset
    config_type = HarborEvaluatorConfig

    evaluator_type: EvaluatorType = "harbor-native"

    def __init__(self, options: HarborEvaluatorConfig | None = None, experiment_dir: Path | None = None) -> None:
        super().__init__(options or HarborEvaluatorConfig(), experiment_dir=experiment_dir)

    async def _run(self, agent: Path, dataset: Dataset, options: EvaluatorConfig) -> Sequence[TrialResult]:
        # Widened from HarborEvaluatorConfig to match the base class contract:
        # Evaluator.run() passes an EvaluatorConfig instance through unchanged, so
        # narrowing here would be an unsound override. The guard is defensive only —
        # both the factory and the loop build this config via type(self.options).
        if not isinstance(options, HarborEvaluatorConfig):
            raise TypeError("Options must be a HarborEvaluatorConfig")

        inputs = await resolve_harbor_run_inputs(agent, dataset, options, self.experiment_dir)
        harbor_dataset = inputs.dataset
        dataset_path = inputs.dataset_path
        agent_path = inputs.agent_path

        options_dict = options.model_dump()
        options_dict["jobs_dir"] = inputs.jobs_dir
        options_dict["job_name"] = inputs.job_name
        import_path: str = options_dict.pop("import_path")
        trace_dir: str = options_dict.pop("trace_dir", DEFAULT_TRACE_ARTIFACT_SOURCE)
        trace_format: str = options_dict.pop("trace_format", "otlp")
        options_dict["artifacts"] = _with_trace_artifact(options_dict.get("artifacts") or [], trace_dir)
        # Nothing else tells a verifier where the traces are.
        options_dict["verifier"] = VerifierConfig(env={"TRACE_DIR": trace_dir})
        force_rerun: bool = options_dict.pop("force_rerun", False)

        scoped_import_path, scoped_package = _scoped_import_path(agent_path, import_path)
        agents_config = [AgentConfig(import_path=scoped_import_path)]
        datasets_config = [DatasetConfig(path=dataset_path, task_names=[task.id for task in harbor_dataset.tasks])]
        job_config = JobConfig(**options_dict, agents=agents_config, datasets=datasets_config)
        if force_rerun:
            job_dir = _validated_job_dir(job_config.jobs_dir, job_config.job_name)
            if job_dir.exists():
                shutil.rmtree(job_dir)

        try:
            job = await Job.create(job_config)
            await job.run()
        finally:
            _cleanup_scoped_imports(scoped_package)

        trials = await self._trials_from_dir(job.job_dir, harbor_dataset.tasks, trace_format=trace_format)
        return trials

    async def _trials_from_dir(
        self,
        job_dir: Path,
        tasks: Sequence[Task],
        *,
        trace_format: str = "otlp",
    ) -> Sequence[TrialResult]:
        return trials_from_job_dir(job_dir, tasks, trace_format=trace_format)
