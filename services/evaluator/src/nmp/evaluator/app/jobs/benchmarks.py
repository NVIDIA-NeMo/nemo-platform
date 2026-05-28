# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Job compiler for benchmark evaluation jobs.

Compiles BenchmarkJob to PlatformJobSpec for execution by the Jobs service.
"""

import nmp.evaluator.app.values as app
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
from nmp.evaluator.tasks.evaluate_benchmark import (
    benchmark_evaluation_entrypoint,
    benchmark_evaluation_entrypoint_args,
)


async def compile_benchmark_job(job: app.BenchmarkJob) -> PlatformJobSpec:
    """Compile a benchmark job input to a platform job spec.

    Args:
        job: The benchmark job input.
        benchmark: The resolved benchmark entity.

    Returns:
        Platform job specification ready for execution.
    """
    steps: list[PlatformJobStep] = []

    # Add fileset download step for the benchmark's dataset
    steps.append(get_fileset_step(job.benchmark.dataset, step_name="dataset-download"))
    steps.append(await _get_benchmark_evaluation_step(job))

    return PlatformJobSpec(steps=steps)


async def _get_benchmark_evaluation_step(job: app.BenchmarkJob) -> PlatformJobStep:
    """Create the step for a benchmark job for evaluation and results handling.

    Args:
        job: The benchmark job input.
        benchmark: The resolved benchmark entity.

    Returns:
        Platform job step for benchmark evaluation.
    """
    # Determine job type for metric instantiation
    job_type = job.__job_type__
    benchmark = job.benchmark

    # Collect secrets from all metrics in the benchmark using the MetricWithSecrets protocol
    secret_envs: list[EnvironmentVariable] = []

    for benchmark_metric in benchmark.metrics:
        metric_config = benchmark_metric.metric
        # Create metric instance without resolving secrets (they'll be injected at runtime)
        metric = await new_metric(metric_config, job_type, secret_resolver=None)

        # Extract secrets using the MetricWithSecrets protocol
        if isinstance(metric, MetricWithSecrets):
            for secret_env, secret in metric.secrets().items():
                secret_envs.append(
                    EnvironmentVariable(
                        name=secret_env,
                        from_secret=EnvironmentVariableFromSecret(name=secret.root),
                    )
                )

    # Handle target model secret for online jobs
    if isinstance(job, app.BenchmarkOnlineJob):
        if job.model.api_key_secret:
            env_var_name = job.model.api_key_env
            assert env_var_name is not None
            secret_envs.append(
                EnvironmentVariable(
                    name=env_var_name,
                    from_secret=EnvironmentVariableFromSecret(name=job.model.api_key_secret.root),
                )
            )

    # Deduplicate secrets by name
    seen_secrets: set[str] = set()
    unique_secret_envs: list[EnvironmentVariable] = []
    for env in secret_envs:
        if env["name"] not in seen_secrets:
            seen_secrets.add(env["name"])
            unique_secret_envs.append(env)

    return PlatformJobStep(
        name="evaluation",
        executor=CPUExecutionProviderSpec(
            provider="cpu",
            container=ContainerSpec(
                image=get_qualified_image("nmp-cpu-tasks"),
                entrypoint=benchmark_evaluation_entrypoint(),
                command=benchmark_evaluation_entrypoint_args(
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
            *unique_secret_envs,
        ],
    )
