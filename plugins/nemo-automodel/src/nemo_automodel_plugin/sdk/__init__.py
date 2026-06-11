# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Automodel contributor SDK (mounted under ``client.customization`` by nemo-customizer)."""

from nemo_automodel_plugin.sdk.resources import (
    AsyncAutomodelCustomization,
    AsyncAutomodelJobsResource,
    AutomodelCustomization,
    AutomodelJobsResource,
)

__all__ = [
    "AsyncAutomodelCustomization",
    "AsyncAutomodelJobsResource",
    "AutomodelCustomization",
    "AutomodelJobsResource",
]
