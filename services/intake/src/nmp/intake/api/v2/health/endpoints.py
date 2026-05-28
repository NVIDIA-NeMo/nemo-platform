# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Health check endpoints."""

from fastapi import APIRouter, status

router = APIRouter()

API_TAG = "Health Checks"


@router.get(
    "/health/live",
    tags=[API_TAG],
    status_code=status.HTTP_200_OK,
    summary="Perform a simple liveness check to verify the server is running.",
)
@router.get(
    "/v1/health/live",
    tags=[API_TAG],
    status_code=status.HTTP_200_OK,
    summary="Perform a simple liveness check to verify the server is running.",
)
async def health_live() -> dict:
    """
    Health check endpoint to verify the status of the application.
    """
    return {"status": "healthy"}


@router.get(
    "/health/ready",
    tags=[API_TAG],
    status_code=status.HTTP_200_OK,
    summary="Perform a readiness check to verify the server is able/ready to serve requests.",
)
@router.get(
    "/v1/health/ready",
    tags=[API_TAG],
    status_code=status.HTTP_200_OK,
    summary="Perform a readiness check to verify the server is able/ready to serve requests.",
)
async def health_ready() -> dict:
    """
    Health check endpoint to verify the status of the application.
    """
    return {"status": "ready"}


@router.get(
    "/health",
    tags=[API_TAG],
    status_code=status.HTTP_200_OK,
    summary="Unified health endpoint to check if server is alive and ready to serve requests.",
)
async def health_overall() -> dict:
    """Unified health endpoint."""
    return {"status": "ready"}
