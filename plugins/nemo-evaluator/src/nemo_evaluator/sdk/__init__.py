# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Public Evaluator plugin SDK surface."""

from __future__ import annotations

from typing import TYPE_CHECKING

from nemo_evaluator.sdk.types import (
    ExecutionMode,
    FilesetRef,
    PluginDatasetInput,
    RunConfig,
    RunConfigOnline,
    RunConfigOnlineModel,
)

__all__ = [
    "AsyncEvaluator",
    "AsyncEvaluatorJobResource",
    "Evaluator",
    "EvaluatorJobResource",
    "RunConfig",
    "RunConfigOnline",
    "RunConfigOnlineModel",
    "ExecutionMode",
    "FilesetRef",
    "PluginDatasetInput",
]

if TYPE_CHECKING:
    from nemo_evaluator.sdk.job_resources import AsyncEvaluatorJobResource, EvaluatorJobResource
    from nemo_evaluator.sdk.resources import AsyncEvaluator, Evaluator


def __getattr__(name: str) -> object:
    if name in {"AsyncEvaluatorJobResource", "EvaluatorJobResource"}:
        from nemo_evaluator.sdk.job_resources import AsyncEvaluatorJobResource, EvaluatorJobResource

        return {
            "AsyncEvaluatorJobResource": AsyncEvaluatorJobResource,
            "EvaluatorJobResource": EvaluatorJobResource,
        }[name]

    if name in {"AsyncEvaluator", "Evaluator"}:
        from nemo_evaluator.sdk.resources import AsyncEvaluator, Evaluator

        return {
            "AsyncEvaluator": AsyncEvaluator,
            "Evaluator": Evaluator,
        }[name]

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
