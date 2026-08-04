# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared HTTP helpers for evaluator plugin SDK resources."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote, urljoin

from nemo_evaluator.jobs.evaluate import EvaluateInputSpec
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform

PlatformClient = NeMoPlatform | AsyncNeMoPlatform

_API_PREFIX = "/apis/evaluator"


def base_url(source: str) -> str:
    """Return the normalized base URL for a raw URL string."""
    return source.rstrip("/")


def resolve_workspace(platform: PlatformClient, workspace: str | None, *, strict: bool = False) -> str:
    """Return the explicit, platform, or default workspace for evaluator routes.

    When ``strict`` is true, raise ``ValueError`` instead of falling back to
    ``"default"`` when neither an explicit workspace nor a platform-default
    workspace is available.
    """
    resolved = workspace or platform.workspace
    if resolved is None:
        if strict:
            raise ValueError("workspace must be provided when the client has no default workspace")
        return "default"
    return resolved


def url(platform: PlatformClient, path: str, workspace: str | None = None) -> str:
    """Build a full evaluator plugin API URL for the provided route path."""
    resolved_path = path.format(workspace=resolve_workspace(platform, workspace))
    return _join_url(str(platform.base_url), f"{_API_PREFIX}/{resolved_path}")


def platform_default_headers(platform: PlatformClient) -> dict[str, str]:
    """Return string-valued default platform headers for direct evaluator HTTP calls."""
    return {str(key): value for key, value in platform.default_headers.items() if isinstance(value, str)}


def create_job_payload(spec: EvaluateInputSpec) -> dict[str, dict[str, Any]]:
    """Serialize an evaluator job creation request body."""
    return {"spec": spec.model_dump(mode="json")}


#: Job collections the evaluator plugin exposes, matching each job's ``job_collection_path``.
DATASET_JOB_COLLECTION = "evaluate"
TASKSET_JOB_COLLECTION = "agent-evaluate"


def job_collection_url(*, raw_base_url: str, workspace: str, collection: str = DATASET_JOB_COLLECTION) -> str:
    """Build the create/list URL for one of the plugin's job collections."""
    encoded_workspace = quote(workspace, safe="")
    return _join_url(raw_base_url, f"{_API_PREFIX}/v2/workspaces/{encoded_workspace}/{collection}/jobs")


def job_route_base_url(
    *, raw_base_url: str, workspace: str, job_name: str, collection: str = DATASET_JOB_COLLECTION
) -> str:
    """Build the stable evaluator plugin URL prefix for one submitted job.

    ``collection`` selects the job family the name lives under — dataset-driven ``evaluate`` jobs
    and task-driven ``agent-evaluate`` jobs are separate collections on the plugin API, so a job
    name is only resolvable within its own.
    """
    encoded_job_name = quote(job_name, safe="")
    collection_url = job_collection_url(raw_base_url=raw_base_url, workspace=workspace, collection=collection)
    return f"{collection_url}/{encoded_job_name}"


def job_route_resource_url(*, job_base_url: str, resource_path: str) -> str:
    """Build a full evaluator plugin URL below a stable job route."""
    return _join_url(job_base_url, resource_path)


def job_route_url(
    *,
    base_url: str,
    workspace: str,
    job_name: str,
    suffix: str,
    collection: str = DATASET_JOB_COLLECTION,
) -> str:
    """Build a full evaluator plugin job URL for a specific job-scoped operation."""
    return job_route_resource_url(
        job_base_url=job_route_base_url(
            raw_base_url=base_url, workspace=workspace, job_name=job_name, collection=collection
        ),
        resource_path=suffix,
    )


def _join_url(root: str, relative_path: str) -> str:
    """Join a root URL and a relative path using URL parsing rules."""
    return urljoin(f"{base_url(root)}/", relative_path.lstrip("/"))
