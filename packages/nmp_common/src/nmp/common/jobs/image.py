# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Backward-compat re-exports — canonical home is nemo_platform_plugin.jobs.image.

New code (especially plugins) should import directly from
nemo_platform_plugin.jobs.image to avoid pulling nmp-common's server-side
deps. Service callers can keep this import path for now.
"""

from nemo_platform_plugin.jobs.image import get_qualified_image as get_qualified_image
from nemo_platform_plugin.jobs.image import image_builder as image_builder
