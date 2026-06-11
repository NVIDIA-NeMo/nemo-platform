# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Configuration namespace for the evaluator plugin."""

from __future__ import annotations

from typing import ClassVar

from nemo_platform_plugin.config import NemoConfig


class EvaluatorConfig(NemoConfig):
    """Configuration namespace for the evaluator plugin."""

    plugin_name: ClassVar[str] = "evaluator"
    plugin_description: ClassVar[str] = "Configuration namespace for the evaluator plugin."
