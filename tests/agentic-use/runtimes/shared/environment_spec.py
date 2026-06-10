# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Compatibility shim — environment authoring was promoted to the Evaluator SDK.

Import from ``nemo_evaluator_sdk.agent_eval.runtimes.environment_spec`` directly;
this module re-exports the same symbols so existing adapter imports keep working.
"""

from __future__ import annotations

from nemo_evaluator_sdk.agent_eval.runtimes.environment_spec import (
    DEFAULT_DOCKERFILE_RELPATH,
    ENVIRONMENT_SPEC_FILENAME,
    BuildPlan,
    EnvironmentSpec,
    execute_build_plan,
    load_environment_spec,
    plan_task_build,
    render_derived_dockerfile,
)

__all__ = [
    "DEFAULT_DOCKERFILE_RELPATH",
    "ENVIRONMENT_SPEC_FILENAME",
    "BuildPlan",
    "EnvironmentSpec",
    "execute_build_plan",
    "load_environment_spec",
    "plan_task_build",
    "render_derived_dockerfile",
]
