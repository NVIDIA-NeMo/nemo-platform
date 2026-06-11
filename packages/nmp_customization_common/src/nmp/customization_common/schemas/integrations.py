# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared experiment-tracking integrations schema for customization job input.

One opinionated integrations object used by both backends so a job spec means
the same thing on either. Backends consume whichever fields apply (Automodel
reads ``wandb`` / ``mlflow``; Unsloth's trl driver also honours ``report_to``).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class WandbIntegration(BaseModel):
    """Weights & Biases tracking configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    project: str | None = None
    api_key_secret: str | None = None
    run_name: str | None = None


class IntegrationsSpec(BaseModel):
    """Experiment-tracking integrations for a customization job."""

    model_config = ConfigDict(extra="forbid")

    wandb: WandbIntegration | None = None
    mlflow: dict[str, Any] | None = None
    # trl/HF ``report_to`` selector (consumed by the Unsloth backend).
    report_to: list[Literal["wandb", "tensorboard", "mlflow", "none"]] | None = None
