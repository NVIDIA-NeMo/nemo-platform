# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Entities service MCP server implementation.

This module provides MCP tools for the entities service, including workspace
discovery and management operations.
"""

from __future__ import annotations

import logging
from typing import Any

from fastmcp import FastMCP
from nmp.common.mcp import format_error_response
from nmp.common.sdk_factory import get_platform_sdk

logger = logging.getLogger(__name__)


def create_server(base_url: str | None = None) -> FastMCP:
    """
    Create and configure the entities service MCP server.

    This server provides tools for workspace discovery and entity management
    operations exposed by the entities service.

    Args:
        base_url: Optional NeMo platform base URL

    Returns:
        Configured FastMCP server instance with entities tools registered
    """
    # Initialize FastMCP server for entities service
    server = FastMCP("NeMo Entities Service")

    # Create NeMo SDK client using shared factory
    nemo_client = get_platform_sdk(base_url=base_url)

    # === WORKSPACE TOOLS ===

    @server.tool(description="List workspaces in the NeMo platform")
    async def list_workspaces(
        page: int = 1,
        page_size: int = 50,
        search_by_like: str | None = None,
    ) -> dict[str, Any]:
        """
        List all workspaces available in the NeMo Platform.

        This is a read-only operation that retrieves workspace information including
        IDs, descriptions, and metadata.

        Args:
            page: Page number to retrieve (default: 1)
            page_size: Number of items per page (default: 50)
            search_by_like: Optional search filter using SQL LIKE syntax (e.g., "%prod%")

        Returns:
            Dictionary containing:
            - success: Boolean indicating if the operation succeeded
            - workspaces: List of workspace objects with id, description, etc.
            - total: Total number of workspaces matching the filter
            - page: Current page number
            - page_size: Items per page
        """
        try:
            # Call the SDK to list workspaces with pagination and filtering
            response = nemo_client.workspaces.list(
                page=page,
                page_size=page_size,
                filter=search_by_like,
            )

            # Extract workspace data from response.data
            workspaces = []
            for workspace in response.data:
                workspaces.append(
                    {
                        "id": workspace.id,
                        "name": workspace.name,
                        "description": workspace.description,
                        "created_at": str(workspace.created_at) if hasattr(workspace, "created_at") else None,
                    }
                )

            # Get total count from pagination if available, otherwise use length
            total = len(workspaces)
            if hasattr(response, "pagination") and response.pagination is not None:
                if hasattr(response.pagination, "total_results"):
                    total = response.pagination.total_results

            return {
                "success": True,
                "workspaces": workspaces,
                "total": total,
                "page": page,
                "page_size": page_size,
            }
        except Exception as e:
            return format_error_response(e)

    @server.tool(description="Create a new workspace in the NeMo platform")
    async def create_workspace(
        name: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a new workspace in the NeMo Platform.

        Workspaces are the fundamental organizational boundary. All resources
        (models, datasets, jobs, etc.) must belong to a workspace.

        Args:
            name: Unique workspace name. Must follow RFC 1035 DNS label rules:
                  lowercase alphanumeric and hyphens, starting with a letter,
                  max 63 characters. Cannot be changed after creation.
            description: Optional free-form text describing the workspace's purpose.

        Returns:
            Dictionary containing:
            - success: Boolean indicating if the operation succeeded
            - workspace: Created workspace object with id, name, description
            - message: Human-readable success message
        """
        try:
            # Call the SDK to create the workspace
            workspace = nemo_client.workspaces.create(
                name=name,
                description=description,
            )

            return {
                "success": True,
                "workspace": {
                    "id": workspace.id,
                    "name": workspace.name,
                    "description": workspace.description,
                    "created_at": str(workspace.created_at) if hasattr(workspace, "created_at") else None,
                },
                "message": f"Workspace '{name}' created successfully",
            }
        except Exception as e:
            return format_error_response(e)

    @server.tool(description="Delete a workspace from the NeMo platform")
    async def delete_workspace(
        name: str,
    ) -> dict[str, Any]:
        """
        Delete a workspace from the NeMo Platform.

        WARNING: This is a destructive operation. Deleting a workspace will also
        delete all resources contained within it (models, datasets, jobs, etc.).

        Args:
            name: Name of the workspace to delete.

        Returns:
            Dictionary containing:
            - success: Boolean indicating if the operation succeeded
            - message: Human-readable success/error message
        """
        try:
            # Call the SDK to delete the workspace
            nemo_client.workspaces.delete(name)

            return {
                "success": True,
                "message": f"Workspace '{name}' deleted successfully",
            }
        except Exception as e:
            return format_error_response(e)

    return server
