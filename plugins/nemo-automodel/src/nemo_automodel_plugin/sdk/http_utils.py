# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared HTTP helpers for Automodel customization SDK resources."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote, urljoin

from nemo_platform import AsyncNeMoPlatform, NeMoPlatform

from nemo_automodel_plugin.schema import AutomodelJobInput

PlatformClient = NeMoPlatform | AsyncNeMoPlatform

_API_PREFIX = "/apis/customization"
_JOBS_COLLECTION = "v2/workspaces/{workspace}/automodel/jobs"


def base_url(source: str) -> str:
    """Return the normalized base URL for a raw URL string."""
    return source.rstrip("/")


def resolve_workspace(platform: PlatformClient, workspace: str | None, strict: bool = False) -> str:
    """Return the explicit, platform, or default workspace for customization routes."""
    resolved = workspace or platform.workspace
    if resolved is None:
        if strict:
            raise ValueError("workspace must be provided when the client has no default workspace")
        return "default"
    return resolved


def url(platform: PlatformClient, path: str, workspace: str | None = None) -> str:
    """Build a full customization plugin API URL for the provided route path."""
    resolved_path = path.format(workspace=quote(resolve_workspace(platform, workspace), safe=""))
    return _join_url(str(platform.base_url), f"{_API_PREFIX}/{resolved_path}")


def jobs_collection_url(platform: PlatformClient, workspace: str | None = None) -> str:
    """URL for the Automodel jobs collection in a workspace."""
    return url(platform, _JOBS_COLLECTION, workspace)


def job_url(platform: PlatformClient, job_name: str, workspace: str | None = None) -> str:
    """URL for a single Automodel job."""
    return _join_url(jobs_collection_url(platform, workspace), quote(job_name, safe=""))


def platform_default_headers(platform: PlatformClient) -> dict[str, str]:
    """Return string-valued default platform headers for direct HTTP calls."""
    return {str(key): value for key, value in platform.default_headers.items() if isinstance(value, str)}


def create_job_payload(spec: AutomodelJobInput) -> dict[str, dict[str, Any]]:
    """Serialize an Automodel job creation request body."""
    return {"spec": spec.model_dump(mode="json")}


def _join_url(root: str, relative_path: str) -> str:
    """Join a root URL and a relative path using URL parsing rules."""
    return urljoin(f"{base_url(root)}/", relative_path.lstrip("/"))
