# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""HTTP helpers for customization contributor SDK resources."""

from typing import Any
from urllib.parse import quote, urljoin

from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from pydantic import BaseModel

PlatformClient = NeMoPlatform | AsyncNeMoPlatform

_API_PREFIX = "/apis/customization"


class CustomizationHttpHelpers:
    """Backend-scoped URL builders for the customization plugin API."""

    def __init__(self, backend: str) -> None:
        self.backend = backend
        self._jobs_collection = f"v2/workspaces/{{workspace}}/{backend}/jobs"

    def base_url(self, source: str) -> str:
        """Return the normalized base URL for a raw URL string."""
        return source.rstrip("/")

    def resolve_workspace(
        self,
        platform: PlatformClient,
        workspace: str | None,
        strict: bool = False,
    ) -> str:
        """Return the explicit, platform, or default workspace for customization routes."""
        resolved = workspace or platform.workspace
        if resolved is None:
            if strict:
                raise ValueError("workspace must be provided when the client has no default workspace")
            return "default"
        return resolved

    def url(self, platform: PlatformClient, path: str, workspace: str | None = None) -> str:
        """Build a full customization plugin API URL for the provided route path."""
        resolved_path = path.format(workspace=quote(self.resolve_workspace(platform, workspace), safe=""))
        return self._join_url(str(platform.base_url), f"{_API_PREFIX}/{resolved_path}")

    def jobs_collection_url(self, platform: PlatformClient, workspace: str | None = None) -> str:
        """URL for the backend jobs collection in a workspace."""
        return self.url(platform, self._jobs_collection, workspace)

    def job_url(self, platform: PlatformClient, job_name: str, workspace: str | None = None) -> str:
        """URL for a single backend job."""
        return self._join_url(self.jobs_collection_url(platform, workspace), quote(job_name, safe=""))

    def healthz_path(self) -> str:
        """Relative API path for contributor health (includes workspace placeholder)."""
        return f"v2/workspaces/{{workspace}}/{self.backend}/healthz"

    def job_status_path(self, base_url: str, workspace: str, job_name: str) -> str:
        """Full URL for fetching one job record (status polling)."""
        encoded_workspace = quote(workspace, safe="")
        encoded_job = quote(job_name, safe="")
        return (
            f"{self.base_url(base_url)}/apis/customization/v2/workspaces/"
            f"{encoded_workspace}/{self.backend}/jobs/{encoded_job}"
        )

    @staticmethod
    def platform_default_headers(platform: PlatformClient) -> dict[str, str]:
        """Return string-valued default platform headers for direct HTTP calls."""
        return {str(key): value for key, value in platform.default_headers.items() if isinstance(value, str)}

    @staticmethod
    def create_job_payload(spec: BaseModel) -> dict[str, dict[str, Any]]:
        """Serialize a job creation request body."""
        return {"spec": spec.model_dump(mode="json")}

    def _join_url(self, root: str, relative_path: str) -> str:
        """Join a root URL and a relative path using URL parsing rules."""
        return urljoin(f"{self.base_url(root)}/", relative_path.lstrip("/"))


def bind_backend(backend: str) -> CustomizationHttpHelpers:
    """Return HTTP helpers scoped to a customization backend name."""
    return CustomizationHttpHelpers(backend)
