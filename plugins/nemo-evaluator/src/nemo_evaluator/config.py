# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Configuration namespace for the evaluator plugin."""

from __future__ import annotations

from typing import ClassVar

from nemo_platform_plugin.config import NemoConfig
from pydantic import Field


class EvaluatorConfig(NemoConfig):
    """Configuration namespace for the evaluator plugin."""

    plugin_name: ClassVar[str] = "evaluator"
    plugin_description: ClassVar[str] = "Configuration namespace for the evaluator plugin."

    gym_tasks_image: str | None = Field(
        default=None,
        description=(
            "Optional fully qualified image reference for Gym agent-evaluation jobs. Override with "
            "NEMO_EVALUATOR_GYM_TASKS_IMAGE; when set, this bypasses platform image registry/tag qualification."
        ),
    )


def get_config() -> EvaluatorConfig:
    """Return the Evaluator plugin configuration singleton."""
    return EvaluatorConfig.get()


config = get_config()
