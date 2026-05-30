# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Entity store client — re-exports from nemo_platform_plugin with platform extensions.

The canonical EntityBase, EntityClient base, and related types live in
nemo_platform_plugin.entities. This module re-exports them and extends EntityClient
with the platform-specific ``as_service()`` method.
"""

from __future__ import annotations

# Re-export types from nemo-platform-plugin (canonical source) that have
# consumers through this module's path.
from nemo_platform_plugin.entities import EntityBase as EntityBase
from nemo_platform_plugin.entities import EntityClient as _PluginEntityClient
from nemo_platform_plugin.entities import EntityConflictError as EntityConflictError
from nemo_platform_plugin.entities import EntityNotFoundError as EntityNotFoundError
from nemo_platform_plugin.entities import EntityStoreError as EntityStoreError
from nemo_platform_plugin.entities import EntityValidationError as EntityValidationError
from nemo_platform_plugin.entities import ListResponse as ListResponse
from nemo_platform_plugin.entities import PaginationInfo as PaginationInfo
from nemo_platform_plugin.entities import parse_qualified_name as parse_qualified_name


class EntityClient(_PluginEntityClient):
    """Extended entity client with platform-specific capabilities.

    Adds ``as_service()`` for service-principal credential elevation,
    which requires ``nmp.common.observability``.
    """

    def as_service(self, service_name: str, *, internal: bool = False) -> "EntityClient":
        """Return a copy with service principal credentials baked in.

        Use this for background tasks, startup code, or permission elevation
        where you need service-level access. The returned client has service
        principal headers (X-NMP-Principal-Id: service:<name>) baked into its
        underlying SDK, so all requests are authenticated as the service.

        Args:
            service_name: The service name (e.g., "auth", "evaluator")
            internal: If True, mark requests as internal to suppress access logging.

        Returns:
            A new EntityClient backed by an SDK with service principal headers.
        """
        from nemo_platform.resources.entities import AsyncEntitiesResource
        from nmp.common.observability import MARK_INTERNAL_REQUEST_HEADERS

        underlying_sdk = self.entities_api._client
        headers: dict[str, str] = {"X-NMP-Principal-Id": f"service:{service_name}"}
        if internal:
            headers.update(MARK_INTERNAL_REQUEST_HEADERS)
        service_sdk = underlying_sdk.with_options(set_default_headers=headers)
        return EntityClient(AsyncEntitiesResource(service_sdk))
