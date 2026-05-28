# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import nmp.evaluator.app.values as app
from nemo_evaluator_sdk.values import Model
from nmp.common.jobs.api_factory import (
    ContainerSpec,
    CPUExecutionProviderSpec,
    EnvironmentVariable,
    EnvironmentVariableFromSecret,
    PlatformJobSpec,
    PlatformJobStep,
)
from nmp.common.jobs.constants import PERSISTENT_JOB_STORAGE_PATH_ENVVAR
from nmp.common.jobs.image import get_qualified_image
from nmp.evaluator.app.jobs.fileset import get_fileset_step
from nmp.evaluator.app.jobs.progress_tracking import get_progress_tracking_url
from nmp.evaluator.app.metrics.metric import MetricWithSecrets, new_metric
from nmp.evaluator.config import settings
from nmp.evaluator.tasks.evaluate_metric import (
    metric_evaluation_entrypoint,
    metric_evaluation_entrypoint_args,
)


async def compile_metric_job(job: app.MetricJob) -> PlatformJobSpec:
    steps: list[PlatformJobStep] = []

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


def get_results_step(job: app.MetricJob | app.BenchmarkJob) -> PlatformJobStep:
    return PlatformJobStep(
        name="results",
        executor=CPUExecutionProviderSpec(
            provider="cpu",
            container=ContainerSpec(
                image=get_qualified_image("nmp-cpu-tasks"),
                entrypoint=["python", "-m", "nmp.evaluator.tasks.metric_results"],
                command=[
                    "--progress-tracking-url",
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
