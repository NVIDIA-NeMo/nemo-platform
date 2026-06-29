# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Read-only metric-type catalog and evaluate-schema discovery routes (mirror the CLI)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status
from nemo_evaluator.authz import scope
from nemo_evaluator.jobs.evaluate import EvaluateInputSpec
from nemo_evaluator.metric_catalog import metric_type_entries, metric_type_schema
from nemo_platform_plugin.authz import CallerKind, path_rule

router = APIRouter()


@router.get(
    "/metric-types",
    summary="List Metric Types",
    response_description="Available built-in metric types and their descriptions",
    status_code=status.HTTP_200_OK,
)
@scope.read
@path_rule(callers=[CallerKind.PRINCIPAL], permissions=[])
async def list_metric_types() -> dict[str, list[dict[str, str]]]:
    """List the built-in evaluator metric types (the same catalog the CLI prints)."""
    return {"metric_types": metric_type_entries()}


@router.get(
    "/metric-types/{metric_type}",
    summary="Get Metric Type Schema",
    response_description="JSON schema for a single metric type",
    status_code=status.HTTP_200_OK,
    responses={status.HTTP_404_NOT_FOUND: {"description": "Unknown metric type"}},
)
@scope.read
@path_rule(callers=[CallerKind.PRINCIPAL], permissions=[])
async def get_metric_type_schema(metric_type: str) -> dict[str, Any]:
    """Return the JSON schema for one built-in metric type."""
    schema = metric_type_schema(metric_type)
    if schema is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown metric type: {metric_type}",
        )
    return schema


@router.get(
    "/evaluate/schema",
    summary="Get Evaluate Input Schema",
    response_description="JSON schema for the evaluate job input spec",
    status_code=status.HTTP_200_OK,
)
@scope.read
@path_rule(callers=[CallerKind.PRINCIPAL], permissions=[])
async def get_evaluate_schema() -> dict[str, Any]:
    """Return the JSON schema for the evaluate input spec (the `explain` payload)."""
    return EvaluateInputSpec.model_json_schema()
