# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Automodel job resources for status polling via the customization plugin API."""

from nemo_customizer.shared.sdk.job_resources import (
    AsyncCustomizationJobResource as AsyncAutomodelJobResource,
    CustomizationJobRecord as AutomodelJobRecord,
    CustomizationJobResource as AutomodelJobResource,
)

__all__ = [
    "AsyncAutomodelJobResource",
    "AutomodelJobRecord",
    "AutomodelJobResource",
]
