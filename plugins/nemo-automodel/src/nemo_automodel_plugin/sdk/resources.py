# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Automodel contributor SDK resources (composed by ``nemo-customizer-plugin``)."""

from nemo_customizer.shared.sdk.resources import CustomizationSdkConfig, make_customization_sdk_classes

from nemo_automodel_plugin.schema import AutomodelJobInput

_AutomodelCustomization, _AsyncAutomodelCustomization, AutomodelJobsResource, AsyncAutomodelJobsResource = (
    make_customization_sdk_classes(
        CustomizationSdkConfig(
            backend="automodel",
            display_name="Automodel",
            input_schema=AutomodelJobInput,
        ),
    )
)

AutomodelCustomization = _AutomodelCustomization
AsyncAutomodelCustomization = _AsyncAutomodelCustomization

__all__ = [
    "AsyncAutomodelCustomization",
    "AsyncAutomodelJobsResource",
    "AutomodelCustomization",
    "AutomodelJobsResource",
]
