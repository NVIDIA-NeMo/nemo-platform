# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Low-level typed HTTP clients for the Entity Store service.

Wraps the endpoint functions from ``entities.endpoints`` as direct methods via
the ``method()`` descriptor, following the files-service ``FilesClient`` pattern.
These are the transport layer; the ergonomic, entity-model-aware wrapper is
``EntityStoreResource`` in ``entities.resource``.
"""

from nemo_platform_plugin.client.client import AsyncNemoClient, NemoClient
from nemo_platform_plugin.client.method import method
from nemo_platform_plugin.entities import endpoints


class _EntitiesMethods:
    create_entity = method(endpoints.create_entity)
    list_entities = method(endpoints.list_entities)
    get_entity_by_name = method(endpoints.get_entity_by_name)
    get_entity_by_id = method(endpoints.get_entity_by_id)
    update_entity_by_name = method(endpoints.update_entity_by_name)
    delete_entity_by_name = method(endpoints.delete_entity_by_name)


class EntitiesClient(_EntitiesMethods, NemoClient):
    """Sync low-level client for the Entity Store API."""


class AsyncEntitiesClient(_EntitiesMethods, AsyncNemoClient):
    """Async low-level client for the Entity Store API."""
