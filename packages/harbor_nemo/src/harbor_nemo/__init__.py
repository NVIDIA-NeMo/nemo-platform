# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""A NeMo Platform registry backend for Harbor.

Installing this package registers ``nemo`` under the ``harbor.registry_backends`` entry
point, so the stock Harbor CLI publishes to and runs from NeMo with no change to Harbor::

    export HARBOR_REGISTRY_BACKEND=nemo
    harbor publish ./my-task
    harbor run -d nvidia/my-dataset
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from harbor_nemo.backend import NemoRegistryBackend

__all__ = ["load_backend"]


def load_backend() -> "NemoRegistryBackend":
    """Entry point target: build the backend.

    Imports inside the function rather than at module scope because Harbor resolves entry
    points lazily and only for a backend that was actually selected. A module-level import
    would pull httpx and every Harbor publisher model into any process that merely *lists*
    installed backends — including one using the default Supabase backend.
    """
    from harbor_nemo.backend import NemoRegistryBackend

    return NemoRegistryBackend()
