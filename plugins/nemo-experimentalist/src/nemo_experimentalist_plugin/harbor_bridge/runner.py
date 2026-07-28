# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Trusted server-side Harbor evaluation runner."""

from __future__ import annotations

from pathlib import Path

from harbor.models.task.config import EnvironmentConfig, TaskOS, VerifierEnvironmentMode
from harbor.models.task.task import Task as HarborTask
from harbor.models.task.verifier_mode import resolve_effective_verifier_env_config
from nemo_experimentalist_plugin.experimentalist.components.evaluator.harbor import (
    HarborDataset,
    HarborEvaluator,
    HarborEvaluatorConfig,
)
from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import (
    DatasetRef,
    EvaluationResult,
    local_path_from_uri,
)
from nemo_experimentalist_plugin.harbor_bridge.contracts import HarborBridgeRequest
from nemo_experimentalist_plugin.harbor_bridge.trusted_agent import candidate_agent_import

_COMPOSE_FILENAMES = ("docker-compose.yaml", "docker-compose.yml", "compose.yaml", "compose.yml")


def _validate_environment(environment: EnvironmentConfig, *, context: str) -> None:
    if environment.os != TaskOS.LINUX:
        raise ValueError(f"Harbor bridge accepts only Linux {context}")
    if environment.env:
        raise ValueError(f"Harbor bridge {context} may not import host environment variables")
    if environment.mcp_servers:
        raise ValueError(f"Harbor bridge {context} may not configure MCP servers")
    if environment.gpus or environment.tpu is not None:
        raise ValueError(f"Harbor bridge preview does not accept accelerators in {context}")


def _require_verifier_definition(task: HarborTask, *, step_index: int | None = None) -> None:
    config = task.config
    step = config.steps[step_index] if step_index is not None and config.steps is not None else None
    environment = resolve_effective_verifier_env_config(config, step)
    if environment is None:
        raise ValueError(f"Harbor bridge could not resolve a separate verifier environment: {task.task_dir.name}")
    if environment.docker_image:
        return
    tests_dir = task.paths.tests_dir
    if step is not None:
        step_tests_dir = task.paths.step_tests_dir(step.name)
        if step_tests_dir.exists():
            tests_dir = step_tests_dir
    if not (tests_dir / "Dockerfile").is_file():
        relative = tests_dir.relative_to(task.task_dir) / "Dockerfile"
        raise ValueError(
            f"Harbor bridge separate verifier requires {relative.as_posix()} "
            f"or verifier.environment.docker_image: {task.task_dir.name}"
        )


def _harden_task(task_dir: Path) -> None:
    if any(any(task_dir.rglob(name)) for name in _COMPOSE_FILENAMES):
        raise ValueError(f"Harbor bridge does not accept Docker Compose tasks: {task_dir.name}")

    task = HarborTask(task_dir)
    config = task.config
    _validate_environment(config.environment, context=f"task environment {task_dir.name}")
    if config.verifier.environment is not None:
        _validate_environment(config.verifier.environment, context=f"verifier environment {task_dir.name}")
    if config.verifier.env or config.solution.env:
        raise ValueError(
            f"Harbor bridge task may not import verifier or solution environment variables: {task_dir.name}"
        )
    for index, step in enumerate(config.steps or []):
        if step.verifier.env:
            raise ValueError(f"Harbor bridge task step may not import verifier environment variables: {task_dir.name}")
        if step.verifier.environment is not None:
            _validate_environment(
                step.verifier.environment,
                context=f"step verifier environment {task_dir.name}/{step.name}",
            )
        step.verifier.environment_mode = VerifierEnvironmentMode.SEPARATE
        _require_verifier_definition(task, step_index=index)

    config.verifier.environment_mode = VerifierEnvironmentMode.SEPARATE
    if not config.steps:
        _require_verifier_definition(task)
    (task_dir / "task.toml").write_text(config.model_dump_toml(), encoding="utf-8")


class HarborBridgeRunner:
    """Run a fixed Harbor adapter over validated, request-scoped inputs."""

    async def run(
        self,
        request: HarborBridgeRequest,
        *,
        candidate_dir: Path,
        dataset_dir: Path,
        work_dir: Path,
    ) -> EvaluationResult:
        dataset = HarborDataset.from_ref(
            DatasetRef(
                uri=dataset_dir.resolve().as_uri(),
                metadata={"id": request.request_id, "task_ids": request.task_ids},
            )
        )
        for task in dataset.tasks:
            _harden_task(local_path_from_uri(task.uri, context="Harbor task reference").resolve())
        await dataset.validate()

        with candidate_agent_import(candidate_dir) as trusted_import_path:
            evaluator = HarborEvaluator(
                HarborEvaluatorConfig(
                    job_name=request.request_id,
                    jobs_dir=Path("results"),
                    n_attempts=request.n_attempts,
                    n_concurrent_trials=request.n_concurrent_trials,
                    agent_model_name=request.agent_model_name,
                    quiet=True,
                    verifier_timeout_multiplier=request.verifier_timeout_multiplier,
                    agent_timeout_multiplier=request.agent_timeout_multiplier,
                    agent_setup_timeout_multiplier=request.agent_setup_timeout_multiplier,
                    environment_build_timeout_multiplier=request.environment_build_timeout_multiplier,
                    import_path=trusted_import_path,
                    scope_import_path=False,
                    trace_dir="/app/traces",
                ),
                experiment_dir=work_dir,
            )
            return await evaluator.run(candidate_dir, dataset)
