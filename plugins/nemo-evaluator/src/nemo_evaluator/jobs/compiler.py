# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Plugin-native evaluator job compiler."""

from __future__ import annotations

from nemo_evaluator.jobs.evaluate import EvaluateSpec
from nemo_evaluator_sdk.values import Agent, Model, RunConfig, RunConfigOnline, RunConfigOnlineModel
from nemo_platform_plugin.jobs.api_factory import (
    ContainerSpec,
    CPUExecutionProviderSpec,
    EnvironmentVariable,
    PlatformJobSpec,
    PlatformJobStep,
)
from nemo_platform_plugin.jobs.constants import (
    DEFAULT_JOB_STORAGE_PATH,
    EPHEMERAL_TASK_STORAGE_PATH_ENVVAR,
    PERSISTENT_JOB_STORAGE_PATH_ENVVAR,
)
from nmp.common.jobs.image import get_qualified_image
from nmp.evaluator.app.values import FilesetRef

DATASET_DOWNLOAD_STEP_NAME = "dataset-download"
EVALUATE_STEP_NAME = "evaluate"


def compile_evaluate_job(spec: EvaluateSpec, *, profile: str | None = None) -> PlatformJobSpec:
    """Compile a bundle-native evaluator plugin job."""
    _validate_evaluate_spec(spec)
    steps: list[PlatformJobStep] = []
    if isinstance(spec.dataset, FilesetRef):
        steps.append(_fileset_download_step(spec.dataset))
    steps.append(_evaluate_step(spec, profile))
    return PlatformJobSpec(steps=steps)


def _validate_evaluate_spec(spec: EvaluateSpec) -> None:
    if isinstance(spec.target, Model):
        if spec.prompt_template is None:
            raise ValueError("prompt_template is required when EvaluateSpec.target is a model")
        if not isinstance(spec.params, RunConfigOnlineModel):
            raise TypeError("model target requires RunConfigOnlineModel")
    elif isinstance(spec.target, Agent):
        if spec.prompt_template is None:
            raise ValueError("prompt_template is required when EvaluateSpec.target is an agent")
        if not isinstance(spec.params, RunConfigOnline):
            raise TypeError("agent target requires RunConfigOnline")
    elif not isinstance(spec.params, RunConfig):
        raise TypeError("offline evaluation requires RunConfig")


def _fileset_download_step(dataset: FilesetRef) -> PlatformJobStep:
    scratch_path = "${" + EPHEMERAL_TASK_STORAGE_PATH_ENVVAR + "}"
    target_download_dir = "${" + PERSISTENT_JOB_STORAGE_PATH_ENVVAR + "}/datasets"
    return PlatformJobStep(
        name=DATASET_DOWNLOAD_STEP_NAME,
        executor=CPUExecutionProviderSpec(
            provider="cpu",
            container=ContainerSpec(
                image=get_qualified_image("nmp-cpu-tasks"),
                entrypoint=["python", "-m", "nmp.evaluator.tasks.download_fileset"],
                command=[
                    "--local-dir",
                    scratch_path,
                    "--target-dir",
                    target_download_dir,
                    "--dataset",
                    dataset.model_dump_json(),
                ],
            ),
        ),
        environment=[
            EnvironmentVariable(
                name=PERSISTENT_JOB_STORAGE_PATH_ENVVAR,
                value=DEFAULT_JOB_STORAGE_PATH,
            )
        ],
    )


def _evaluate_step(spec: EvaluateSpec, profile: str | None) -> PlatformJobStep:
    return PlatformJobStep(
        name=EVALUATE_STEP_NAME,
        executor=CPUExecutionProviderSpec(
            profile=profile or "default",
            provider="cpu",
            container=ContainerSpec(
                image=get_qualified_image("nmp-cpu-tasks"),
                entrypoint=["python", "-m"],
                command=["nemo_evaluator.tasks.evaluate"],
            ),
        ),
        config=spec.model_dump(mode="json"),
        environment=[
            EnvironmentVariable(
                name=PERSISTENT_JOB_STORAGE_PATH_ENVVAR,
                value=DEFAULT_JOB_STORAGE_PATH,
            )
        ],
    )
