# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Models backend implemented through nemo-deployments entities.

The concrete backend imports the optional ``nemo_deployments_plugin`` package, so
it is resolved lazily via ``__getattr__``. This keeps the core models service
importable (and its wheel bootable) when the deployments plugin is not installed;
the import only happens when the ``deployments_plugin`` backend is actually
selected.
"""

from typing import Any

from .config import DeploymentsPluginBackendConfigModel as DeploymentsPluginBackendConfigModel

__all__ = ["DeploymentsPluginBackendConfigModel", "DeploymentsPluginServiceBackend"]


def __getattr__(name: str) -> Any:
    if name == "DeploymentsPluginServiceBackend":
        from .backend import DeploymentsPluginServiceBackend

        return DeploymentsPluginServiceBackend
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
