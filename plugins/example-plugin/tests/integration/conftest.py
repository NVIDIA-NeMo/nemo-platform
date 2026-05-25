# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Pytest fixture re-export for the example plugin integration tests.

Re-exporting :func:`igw_plugin_harness` from a project-level ``conftest.py``
is the standard pytest pattern for sharing a fixture across a test package
without importing it at the top of every test module. Listing it in
``__all__`` makes the re-export explicit so it isn't flagged as an unused
import.

The module-scope helpers (``_igw_app_context``, ``_igw_extra_services``)
are re-exported so pytest can resolve :func:`igw_plugin_harness`'s
dependency chain. No services beyond IGW + Models are mounted —
the default empty ``_igw_extra_services`` tuple applies.
"""

from nmp.core.inference_gateway.testing.fixtures import (
    _igw_app_context,
    _igw_extra_services,
    igw_plugin_harness,
)

__all__ = [
    "_igw_app_context",
    "_igw_extra_services",
    "igw_plugin_harness",
]
