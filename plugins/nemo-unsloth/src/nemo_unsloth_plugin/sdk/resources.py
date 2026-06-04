# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unsloth contributor SDK resources (composed by ``nemo-customizer-plugin``)."""

from nemo_customizer.shared.sdk.resources import CustomizationSdkConfig, make_customization_sdk_classes

from nemo_unsloth_plugin.schema import UnslothJobInput

_UnslothCustomization, _AsyncUnslothCustomization, UnslothJobsResource, AsyncUnslothJobsResource = (
    make_customization_sdk_classes(
        CustomizationSdkConfig(
            backend="unsloth",
            display_name="Unsloth",
            input_schema=UnslothJobInput,
        ),
    )
)

UnslothCustomization = _UnslothCustomization
AsyncUnslothCustomization = _AsyncUnslothCustomization

__all__ = [
    "AsyncUnslothCustomization",
    "AsyncUnslothJobsResource",
    "UnslothCustomization",
    "UnslothJobsResource",
]
