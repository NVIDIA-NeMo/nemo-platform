# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Canonical optimize study spec."""

from __future__ import annotations

from typing import Any

from nemo_platform_plugin.refs import OutputTarget
from pydantic import BaseModel, Field, model_validator


class OptimizeSpec(BaseModel):
    """Spec for an Agents optimize study (``nemo agents optimize``)."""

    optimize_config: str | None = Field(
        default=None,
        description="Absolute path to the Fabric-native optimization YAML file on the platform host.",
    )
    optimize_config_inline: dict[str, Any] | None = Field(
        default=None,
        description="The Fabric-native optimization config inline, with the same shape as the "
        "YAML file. Use instead of optimize_config when submitting from a remote client.",
    )
    workspace: str = Field(
        default="default",
        description="Workspace used to fetch a platform agent and for VirtualModel preflight.",
    )
    agent: str | None = Field(
        default=None,
        description="Optional platform agent reference ('name' or 'workspace/name'). "
        "When omitted, the optimization config must include an inline Fabric agent package.",
    )
    output: OutputTarget | None = Field(
        default=None,
        description="Where to publish the study artifacts (optimized config, trials dataframe, "
        "pareto plots, ATIF evidence) once the study succeeds — either a local directory "
        "(path-shaped: starts with '/', './', '../', '~/') or a NeMo Platform fileset "
        "reference ('name' or 'workspace/name').  Filesets are created on demand if missing.  "
        "This is in addition to the per-job artifacts that ``ctx.results.save`` always "
        "registers; it gives remote clients a stable, addressable location to read from.",
    )

    @model_validator(mode="after")
    def _exactly_one_config_source(self) -> "OptimizeSpec":
        if self.optimize_config is None and self.optimize_config_inline is None:
            raise ValueError("Set exactly one of optimize_config or optimize_config_inline; got neither.")
        if self.optimize_config is not None and self.optimize_config_inline is not None:
            raise ValueError("Set exactly one of optimize_config or optimize_config_inline; got both.")
        return self
