# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Image helper utilities for NeMo Platform.

Re-exports from :mod:`nemo_platform_plugin.config` — the canonical
implementation now lives in the plugin package so that plugin authors
can use it without depending on ``nmp-common``.
"""

from nemo_platform_plugin.config import get_qualified_image as get_qualified_image
from nemo_platform_plugin.config import image_builder as image_builder
