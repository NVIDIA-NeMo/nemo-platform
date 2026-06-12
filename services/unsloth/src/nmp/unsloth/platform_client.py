# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Async helpers for resolving model/dataset references against the platform.

Re-exports the shared :mod:`nmp.customization_common.service.platform_client` so existing
``nmp.unsloth.platform_client`` import paths keep working.
"""

from nmp.customization_common.service.platform_client import check_dataset_access, fetch_model_entity

__all__ = ["check_dataset_access", "fetch_model_entity"]
