# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Public configuration types for the v4 evaluator API."""

from __future__ import annotations

from typing import TypeAlias

from nemo_evaluator_sdk.values import (
    Agent,
    Model,
    RunConfig,
    RunConfigOnline,
    RunConfigOnlineModel,
)

_RunConfigT: TypeAlias = RunConfig | RunConfigOnline | RunConfigOnlineModel


def resolve_params(
    params: _RunConfigT | None = None,
    target: Model | Agent | None = None,
) -> _RunConfigT:
    """Return params after validating that they match the selected target mode."""
    if isinstance(target, Model):
        if not isinstance(params, RunConfigOnlineModel):
            raise TypeError("model target requires RunConfigOnlineModel")
        return params
    if isinstance(target, Agent):
        if type(params) is not RunConfigOnline:
            raise TypeError("agent target requires RunConfigOnline")
        return params
    if params is None:
        return RunConfig()
    if type(params) is not RunConfig:
        raise TypeError("offline evaluation requires RunConfig")
    return params


def fail_fast_from_params(params: _RunConfigT) -> bool:
    """
    Return whether row failures should abort execution for the given params.
    When params is not an online params, return fail_fast is True - always fail fast.
    """
    return not (isinstance(params, RunConfigOnline) and params.ignore_request_failure)
