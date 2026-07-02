# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""FastAPI dependencies for the evaluator metrics API."""

from __future__ import annotations

from fastapi import Depends
from nemo_evaluator.api.service.metric_service import MetricService
from nemo_evaluator.api.service.result_service import ResultService
from nemo_platform import AsyncNeMoPlatform
from nemo_platform_plugin.dependencies import get_entity_client, get_sdk_client
from nemo_platform_plugin.entities import EntityClient


def get_metric_service(
    entity_client: EntityClient = Depends(get_entity_client),
    sdk: AsyncNeMoPlatform = Depends(get_sdk_client),
) -> MetricService:
    """Provide a MetricService wired to the Entity Store and Files service."""
    return MetricService(entity_client, sdk)


def get_result_service(
    entity_client: EntityClient = Depends(get_entity_client),
) -> ResultService:
    """Provide a ResultService wired to the Entity Store (read-only over result entities)."""
    return ResultService(entity_client)
