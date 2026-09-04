# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Extended ModelsResource with high-level helper methods.

This module provides extended ModelsResource and AsyncModelsResource
classes that include convenience methods for OpenAI integration and
deployment management.

Located at: nemo_platform/models/ (after vendoring)
"""

from .resources import AsyncModelsResource as AsyncModelsResource
from .resources import ModelsResource as ModelsResource
from .resources import ResolvedModelReference as ResolvedModelReference
from .resources import first_provider_ref as first_provider_ref
from .resources import parse_workspace_name_ref as parse_workspace_name_ref
