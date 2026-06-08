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
    EnvironmentVariableFromSecret,
    PlatformJobSpec,
    PlatformJobStep,
)
from nemo_platform_plugin.jobs.constants import (
    DEFAULT_JOB_STORAGE_PATH,
    PERSISTENT_JOB_STORAGE_PATH_ENVVAR,
)
from nemo_platform_plugin.jobs.image import get_qualified_image

EVALUATE_STEP_NAME = "evaluate"
_RESERVED_SECRET_ENV_NAMES = frozenset({PERSISTENT_JOB_STORAGE_PATH_ENVVAR})


def compile_evaluate_job(spec: EvaluateSpec, *, profile: str | None = None) -> PlatformJobSpec:
    """Compile a bundle-native evaluator plugin job."""
    _validate_evaluate_spec(spec)
    return PlatformJobSpec(steps=[_evaluate_step(spec, profile)])


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


def _add_secret_ref(secret_refs: dict[str, str], env_name: str, secret_name: str) -> None:
    if env_name in _RESERVED_SECRET_ENV_NAMES:
        raise ValueError(f"{env_name!r} is reserved and cannot be sourced from secret refs")
    existing = secret_refs.get(env_name)
    if existing is not None and existing != secret_name:
        raise ValueError(f"conflicting secret references for environment variable {env_name!r}")
    secret_refs[env_name] = secret_name


def _secret_environment(spec: EvaluateSpec) -> list[EnvironmentVariable]:
    environment = [
        EnvironmentVariable(
            name=PERSISTENT_JOB_STORAGE_PATH_ENVVAR,
            value=DEFAULT_JOB_STORAGE_PATH,
        )
    ]
    secret_refs: dict[str, str] = {}
    for bundle in spec.metrics:
        for env_name, secret_ref in bundle.secrets.items():
            _add_secret_ref(secret_refs, env_name, secret_ref.root)

    if isinstance(spec.target, Model | Agent) and spec.target.api_key_secret is not None and spec.target.api_key_env:
        _add_secret_ref(secret_refs, spec.target.api_key_env, spec.target.api_key_secret.root)

    environment.extend(
        EnvironmentVariable(name=env_name, from_secret=EnvironmentVariableFromSecret(name=secret_name))
        for env_name, secret_name in sorted(secret_refs.items())
    )
    return environment


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
        environment=_secret_environment(spec),
    )
