# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import os
import shlex
from typing import Tuple

import nmp.evaluator.app.values as app
import yaml
from nemo_evaluator_sdk.enums import MetricType
from nemo_evaluator_sdk.values import Model
from nemo_platform_plugin.jobs.api_factory import (
    ContainerSpec,
    CPUExecutionProviderSpec,
    EnvironmentVariable,
    EnvironmentVariableFromSecret,
    PlatformJobSpec,
    PlatformJobStep,
)
from nemo_platform_plugin.jobs.image import get_qualified_image
from nmp.common.jobs.constants import PERSISTENT_JOB_STORAGE_PATH_ENVVAR
from nmp.evaluator.app.evalfactory.system import get_system_metric_handler
from nmp.evaluator.app.jobs.constants import (
    EVALFACTORY_EVALUATION_JOB_FILE_NAME,
    NEMO_EVAL_FACTORY_JOB_CONFIG,
    NEMO_EVAL_HARNESS,
    EvalHarness,
    resolve_eval_harness,
)
from nmp.evaluator.app.jobs.fileset import get_fileset_step
from nmp.evaluator.app.jobs.progress_tracking import get_progress_tracking_url
from nmp.evaluator.app.metrics.metric import MetricWithSecrets, new_metric
from nmp.evaluator.config import settings
from nmp.evaluator.tasks.evaluate_metric import (
    metric_evaluation_entrypoint,
    metric_evaluation_entrypoint_args,
)

# System metric types that require EvalFactory execution
_SYSTEM_METRIC_TYPES = (MetricType.SYSTEM, MetricType.SYSTEM_RETRIEVER)


async def compile_metric_job(job: app.MetricJob) -> PlatformJobSpec:
    steps: list[PlatformJobStep] = []

    # Dispatch based on metric type, not job type
    # System metrics (SYSTEM, SYSTEM_RETRIEVER) run in EvalFactory containers
    is_system_metric = job.metric.type in _SYSTEM_METRIC_TYPES

    if is_system_metric:
        # EvalFactory execution - system metrics run in specialized containers
        dataset = getattr(job, "dataset", None)
        if dataset is not None and not isinstance(dataset, app.BuiltInDataset):
            steps.append(get_fileset_step(dataset, step_name="dataset-download"))
        steps.append(await get_evalfactory_step(job))
        steps.append(get_results_step(job, eval_harness=resolve_eval_harness(job.metric.labels)))
    else:
        # Local execution - custom metrics run in the CPU tasks container
        dataset = getattr(job, "dataset", None)
        if isinstance(dataset, (app.FilesetRef, app.Fileset)):
            steps.append(get_fileset_step(dataset, step_name="dataset-download"))
        steps.append(await get_metric_step(job))

    return PlatformJobSpec(steps=steps)


async def get_metric_step(job: app.MetricJob) -> PlatformJobStep:
    # Don't resolve secrets during job compilation - they'll be injected as
    # environment variables into the container at runtime
    metric = await new_metric(job.metric, job.__job_type__, secret_resolver=None)

    # Prepare any secrets
    secret_envs = []
    model_secret_env = _get_model_env_secret(job)
    if model_secret_env:
        secret_envs.append(model_secret_env)
    if isinstance(metric, MetricWithSecrets):
        for secret_env, secret in metric.secrets().items():
            secret_envs.append(
                EnvironmentVariable(name=secret_env, from_secret=EnvironmentVariableFromSecret(name=secret.root))
            )

    return PlatformJobStep(
        name="evaluation",
        executor=CPUExecutionProviderSpec(
            provider="cpu",
            container=ContainerSpec(
                image=get_qualified_image("nmp-cpu-tasks"),
                entrypoint=metric_evaluation_entrypoint(),
                command=metric_evaluation_entrypoint_args(
                    progress_tracking_url=get_progress_tracking_url(),
                ),
            ),
        ),
        config=job.model_dump(mode="json", exclude_none=True),
        environment=[
            # Override default shared volume env for steps
            EnvironmentVariable(name=PERSISTENT_JOB_STORAGE_PATH_ENVVAR, value=settings.jobs.volume_path),
            # Use JSON log format for cleaner OTLP log output
            EnvironmentVariable(name="LOG_FORMAT", value="json"),
            *secret_envs,
        ],
    )


async def get_evalfactory_step(job: app.MetricJob) -> PlatformJobStep:
    """Prepare evaluation container for EvalFactory.

    This handles any job with a system metric (type=SYSTEM, SYSTEM_RETRIEVER).
    The metric type determines which EvalFactory handler to use.
    """
    if not isinstance(job.metric, app.SystemMetric):
        raise ValueError(
            f"Expected a SystemMetric for EvalFactory execution, but got {type(job.metric).__name__} "
            f"(type={getattr(job.metric, 'type', 'unknown')}). "
            f"This can happen if the metric reference failed to resolve to a system metric."
        )
    handler = get_system_metric_handler(job.metric.name)

    # Transform Evaluator API to EvalFactory configuration
    ef_job_config = handler.augment_metric_job(job, settings.jobs.results_dir)
    evaluation_config_dict = ef_job_config.model_dump(mode="json", exclude_unset=True, exclude_defaults=True)

    # Prepare evaluation container command
    config_file_command_str, config_file_path = generate_config_file_from_env_command_str()
    container_command = handler.container_command(ef_job_config, config_file_path)
    # Use `exec` so /bin/sh is replaced by eval-factory command as the process-group leader.
    # Otherwise, SIGTERM terminates the /bin/sh before eval-factory finishes graceful shutdown.
    # Once /bin/sh is killed, launcher exits killing the eval-factory process.
    command = ["/bin/sh", "-c", config_file_command_str + " && exec " + shlex.join(container_command)]

    # Prepare any secrets
    secret_envs = []
    model_secret_env = _get_model_env_secret(job)
    if model_secret_env:
        secret_envs.append(model_secret_env)
    for secret_env, secret in handler.metric_job_secrets(job).items():
        secret_envs.append(
            EnvironmentVariable(
                name=secret_env,
                from_secret=EnvironmentVariableFromSecret(name=secret.root),
            )
        )

    return PlatformJobStep(
        name="evaluation",
        executor=CPUExecutionProviderSpec(
            provider="cpu",
            container=ContainerSpec(
                image=handler.docker_image(),
                command=command,
            ),
        ),
        config=evaluation_config_dict,
        environment=[
            # Override default shared volume env for steps
            EnvironmentVariable(name=PERSISTENT_JOB_STORAGE_PATH_ENVVAR, value=settings.jobs.volume_path),
            EnvironmentVariable(name=NEMO_EVAL_FACTORY_JOB_CONFIG, value=yaml.safe_dump(evaluation_config_dict)),
            *secret_envs,
        ],
    )


def get_results_step(job: app.MetricJob | app.BenchmarkJob, eval_harness: EvalHarness) -> PlatformJobStep:
    return PlatformJobStep(
        name="results",
        executor=CPUExecutionProviderSpec(
            provider="cpu",
            container=ContainerSpec(
                image=get_qualified_image("nmp-cpu-tasks"),
                entrypoint=["python", "-m", "nmp.evaluator.tasks.metric_results"],
                command=[
                    "--progress-tracking-url",  # Update progress % for EvalFactory jobs
                    get_progress_tracking_url(),
                ],
            ),
        ),
        config=job.model_dump(mode="json", exclude_none=True),
        environment=[
            # Override default shared volume env for steps
            EnvironmentVariable(name=PERSISTENT_JOB_STORAGE_PATH_ENVVAR, value=settings.jobs.volume_path),
            # Use JSON log format for cleaner OTLP log output
            EnvironmentVariable(name="LOG_FORMAT", value="json"),
            EnvironmentVariable(name=NEMO_EVAL_HARNESS, value=eval_harness),
        ],
    )


def _get_model_env_secret(job: app.MetricJob) -> EnvironmentVariable | None:
    """Create an environment variable secret for target model API key if it exists.

    Checks for model field on jobs that have one (online and RAG jobs).
    """
    # Check if job has a model field with an API key secret
    model = getattr(job, "model", None)
    if model is None or not model.api_key_secret:
        return None

    # Env var name uses underscores (launcher converts hyphens to underscores)
    assert isinstance(model, Model)
    api_key_env = model.api_key_env
    # api_key_env is computed from api_key_secret and must exist when a secret exists.
    if api_key_env is None:
        raise ValueError("model.api_key_env must be set when model.api_key_secret is configured")
    return EnvironmentVariable(
        name=api_key_env,
        from_secret=EnvironmentVariableFromSecret(name=model.api_key_secret.root),
    )


def generate_config_file_from_env_command_str() -> Tuple[str, str]:
    """
    Command to inject for converting NEMO_EVALUATOR_JOB_CONFIG env with serialized job YAML configuration to file:
    mkdir -p /configs && echo \"$NEMO_EVALUATOR_JOB_CONFIG\" > /configs/evaluation_job_file.yaml

    Workaround until config file is supported natively, like K8s ConfigMap.
    """
    config_file_path = os.path.join(settings.jobs.configs_dir, EVALFACTORY_EVALUATION_JOB_FILE_NAME)
    # evaluator image does not have bash and uses shell
    # echo -e is only supported with bash, wrap with double quote to preserve \n instead for shell
    command_str = f'mkdir -p {settings.jobs.configs_dir} && echo "${NEMO_EVAL_FACTORY_JOB_CONFIG}" > {config_file_path}'
    return command_str, config_file_path
