# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""NGC helpers for model deployments (re-export shared resolver)."""

from nemo_platform_plugin.secrets.ngc import resolve_ngc_api_key

__all__ = ["resolve_ngc_api_key"]
