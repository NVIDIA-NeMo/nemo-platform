# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Parametrized customization jobs-collection SDK client.

Both the unsloth and automodel contributor plugins expose an identical
``client.customization.<backend>`` SDK namespace — a jobs collection whose only
backend-specific variable is the route segment (``unsloth`` / ``automodel``).
This module collapses the three previously-duplicated SDK files
(``http_utils`` / ``job_resources`` / ``resources``) into one factory.

Each plugin keeps a thin ``nemo_<svc>_plugin/sdk/resources.py`` shim that calls
:func:`make_customization_sdk` and re-exports ``<Svc>Customization`` /
``Async<Svc>Customization`` — the symbols the ``nemo-customizer`` SDK hub imports
by string.
"""

from typing import Any, ClassVar
from urllib.parse import quote, urljoin

from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform_plugin.jobs.schemas import PlatformJobStatusResponse
from pydantic import BaseModel

PlatformClient = NeMoPlatform | AsyncNeMoPlatform

_API_PREFIX = "/apis/customization"


# --------------------------------------------------------------------------- #
# URL / payload helpers
# --------------------------------------------------------------------------- #
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


def _join_url(root: str, relative_path: str) -> str:
    """Join a root URL and a relative path using URL parsing rules."""
    return urljoin(f"{base_url(root)}/", relative_path.lstrip("/"))


def url(platform: PlatformClient, path: str, workspace: str | None = None) -> str:
    """Build a full customization plugin API URL for the provided route path."""
    resolved_path = path.format(workspace=quote(resolve_workspace(platform, workspace), safe=""))
    return _join_url(str(platform.base_url), f"{_API_PREFIX}/{resolved_path}")


def jobs_collection_url(platform: PlatformClient, backend: str, workspace: str | None = None) -> str:
    """URL for the backend's jobs collection in a workspace."""
    return url(platform, f"v2/workspaces/{{workspace}}/{backend}/jobs", workspace)


def job_url(platform: PlatformClient, backend: str, job_name: str, workspace: str | None = None) -> str:
    """URL for a single backend job."""
    return _join_url(jobs_collection_url(platform, backend, workspace), quote(job_name, safe=""))


def platform_default_headers(platform: PlatformClient) -> dict[str, str]:
    """Return string-valued default platform headers for direct HTTP calls."""
    return {str(key): value for key, value in platform.default_headers.items() if isinstance(value, str)}


def create_job_payload(spec: BaseModel) -> dict[str, Any]:
    """Serialize a job creation request body."""
    return {"spec": spec.model_dump(mode="json")}


def _job_status_path(root: str, backend: str, workspace: str, job_name: str) -> str:
    encoded_workspace = quote(workspace, safe="")
    encoded_job = quote(job_name, safe="")
    return f"{base_url(root)}/apis/customization/v2/workspaces/{encoded_workspace}/{backend}/jobs/{encoded_job}"


# --------------------------------------------------------------------------- #
# Job records / resources
# --------------------------------------------------------------------------- #
class JobRecord(BaseModel):
    """Minimal job record returned by the customization jobs API."""

    name: str
    workspace: str
    status: str | None = None
    spec: dict[str, Any] | None = None


class JobResource:
    """Sync handle for one submitted job."""

    def __init__(
        self,
        backend: str,
        job: JobRecord,
        http_client: Any,
        base_url: str,
        workspace: str,
        headers: dict[str, str],
    ) -> None:
        self._backend = backend
        self.job = job
        self._http_client = http_client
        self._base_url = base_url
        self._workspace = workspace
        self._headers = headers

    def get_status(self) -> PlatformJobStatusResponse:
        """Fetch current job status."""
        response = self._http_client.get(
            _job_status_path(self._base_url, self._backend, self._workspace, self.job.name),
            headers=self._headers,
        )
        response.raise_for_status()
        return PlatformJobStatusResponse.model_validate(response.json())


class AsyncJobResource:
    """Async handle for one submitted job."""

    def __init__(
        self,
        backend: str,
        job: JobRecord,
        http_client: Any,
        base_url: str,
        workspace: str,
        headers: dict[str, str],
    ) -> None:
        self._backend = backend
        self.job = job
        self._http_client = http_client
        self._base_url = base_url
        self._workspace = workspace
        self._headers = headers

    async def get_status(self) -> PlatformJobStatusResponse:
        """Fetch current job status."""
        response = await self._http_client.get(
            _job_status_path(self._base_url, self._backend, self._workspace, self.job.name),
            headers=self._headers,
        )
        response.raise_for_status()
        return PlatformJobStatusResponse.model_validate(response.json())


# --------------------------------------------------------------------------- #
# Jobs collection + customization namespaces (parametrized by backend)
# --------------------------------------------------------------------------- #
class _JobsResourceBase:
    backend: ClassVar[str]
    record_schema: ClassVar[type[JobRecord]] = JobRecord

    _platform: PlatformClient
    # Sync subclass holds an httpx.Client, async holds an httpx.AsyncClient; typed
    # Any so the shared sync/async method bodies (await vs no-await) both check.
    _http_client: Any

    def __init__(self, platform: PlatformClient) -> None:
        self._platform = platform
        self._http_client = platform._client

    def _new_record(self, payload: Any) -> JobRecord:
        return self.record_schema.model_validate(payload)


class JobsResource(_JobsResourceBase):
    """Sync SDK namespace at ``client.customization.<backend>.jobs``."""

    def create(
        self,
        spec: BaseModel,
        workspace: str | None = None,
        name: str | None = None,
    ) -> JobResource:
        """Submit a training job to the platform GPU cluster."""
        body: dict[str, Any] = create_job_payload(spec)
        if name is not None:
            body["name"] = name
        response = self._http_client.post(
            jobs_collection_url(self._platform, self.backend, workspace),
            json=body,
            headers=platform_default_headers(self._platform),
        )
        response.raise_for_status()
        resolved_ws = resolve_workspace(self._platform, workspace)
        return JobResource(
            backend=self.backend,
            job=self._new_record(response.json()),
            http_client=self._http_client,
            base_url=base_url(str(self._platform.base_url)),
            workspace=resolved_ws,
            headers=platform_default_headers(self._platform),
        )

    def get_job_resource(self, job_name: str, workspace: str | None = None) -> JobResource:
        """Get a resource handle for an existing job."""
        resolved_ws = resolve_workspace(self._platform, workspace)
        response = self._http_client.get(
            job_url(self._platform, self.backend, job_name, resolved_ws),
            headers=platform_default_headers(self._platform),
        )
        response.raise_for_status()
        return JobResource(
            backend=self.backend,
            job=self._new_record(response.json()),
            http_client=self._http_client,
            base_url=base_url(str(self._platform.base_url)),
            workspace=resolved_ws,
            headers=platform_default_headers(self._platform),
        )


class AsyncJobsResource(_JobsResourceBase):
    """Async SDK namespace at ``client.customization.<backend>.jobs``."""

    async def create(
        self,
        spec: BaseModel,
        workspace: str | None = None,
        name: str | None = None,
    ) -> AsyncJobResource:
        """Submit a training job to the platform GPU cluster."""
        body: dict[str, Any] = create_job_payload(spec)
        if name is not None:
            body["name"] = name
        response = await self._http_client.post(
            jobs_collection_url(self._platform, self.backend, workspace),
            json=body,
            headers=platform_default_headers(self._platform),
        )
        response.raise_for_status()
        resolved_ws = resolve_workspace(self._platform, workspace)
        return AsyncJobResource(
            backend=self.backend,
            job=self._new_record(response.json()),
            http_client=self._http_client,
            base_url=base_url(str(self._platform.base_url)),
            workspace=resolved_ws,
            headers=platform_default_headers(self._platform),
        )

    async def get_job_resource(self, job_name: str, workspace: str | None = None) -> AsyncJobResource:
        """Get a resource handle for an existing job."""
        resolved_ws = resolve_workspace(self._platform, workspace)
        response = await self._http_client.get(
            job_url(self._platform, self.backend, job_name, resolved_ws),
            headers=platform_default_headers(self._platform),
        )
        response.raise_for_status()
        return AsyncJobResource(
            backend=self.backend,
            job=self._new_record(response.json()),
            http_client=self._http_client,
            base_url=base_url(str(self._platform.base_url)),
            workspace=resolved_ws,
            headers=platform_default_headers(self._platform),
        )


class _CustomizationBase:
    backend: ClassVar[str]
    jobs_resource_cls: ClassVar[type[_JobsResourceBase]]

    def __init__(self, platform: PlatformClient) -> None:
        self.jobs = self.jobs_resource_cls(platform)


def make_customization_sdk(
    backend: str,
    record_schema: type[JobRecord] = JobRecord,
) -> tuple[type[_CustomizationBase], type[_CustomizationBase]]:
    """Build the sync + async ``<Backend>Customization`` SDK namespace classes.

    Returns a ``(sync_cls, async_cls)`` tuple. Each class takes a platform client
    and exposes ``.jobs`` — matching the shape the ``nemo-customizer`` SDK hub
    instantiates as ``client.customization.<backend>``.
    """
    title = backend.capitalize()

    sync_jobs = type(
        f"{title}JobsResource",
        (JobsResource,),
        {"backend": backend, "record_schema": record_schema},
    )
    async_jobs = type(
        f"Async{title}JobsResource",
        (AsyncJobsResource,),
        {"backend": backend, "record_schema": record_schema},
    )
    sync_cls = type(
        f"{title}Customization",
        (_CustomizationBase,),
        {"backend": backend, "jobs_resource_cls": sync_jobs},
    )
    async_cls = type(
        f"Async{title}Customization",
        (_CustomizationBase,),
        {"backend": backend, "jobs_resource_cls": async_jobs},
    )
    return sync_cls, async_cls
