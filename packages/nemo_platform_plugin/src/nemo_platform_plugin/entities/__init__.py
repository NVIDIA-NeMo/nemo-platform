# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Entity Store client package.

Re-exports the legacy Stainless-backed :class:`EntityClient` and shared entity
types (``entities.legacy``) so existing ``from nemo_platform_plugin.entities
import ...`` imports keep working, alongside the new NemoClient-backed
:class:`NemoEntityClient` (``entities.entity_client``).
"""

from nemo_platform_plugin.entities.entity_client import NemoEntityClient as NemoEntityClient
from nemo_platform_plugin.entities.legacy import EntityBase as EntityBase
from nemo_platform_plugin.entities.legacy import EntityClient as EntityClient
from nemo_platform_plugin.entities.legacy import EntityClientProtocol as EntityClientProtocol
from nemo_platform_plugin.entities.legacy import EntityConflictError as EntityConflictError
from nemo_platform_plugin.entities.legacy import EntityNotFoundError as EntityNotFoundError
from nemo_platform_plugin.entities.legacy import EntityStoreError as EntityStoreError
from nemo_platform_plugin.entities.legacy import EntityT as EntityT
from nemo_platform_plugin.entities.legacy import EntityToken as EntityToken
from nemo_platform_plugin.entities.legacy import EntityTypeDefault as EntityTypeDefault
from nemo_platform_plugin.entities.legacy import EntityTypeLike as EntityTypeLike
from nemo_platform_plugin.entities.legacy import EntityValidationError as EntityValidationError
from nemo_platform_plugin.entities.legacy import ListResponse as ListResponse
from nemo_platform_plugin.entities.legacy import PaginationInfo as PaginationInfo
from nemo_platform_plugin.entities.legacy import _convert_filter_obj_to_filter_str as _convert_filter_obj_to_filter_str
from nemo_platform_plugin.entities.legacy import _convert_sort_to_api_sort as _convert_sort_to_api_sort
from nemo_platform_plugin.entities.legacy import _get_entity_type as _get_entity_type
from nemo_platform_plugin.entities.legacy import parse_qualified_name as parse_qualified_name
