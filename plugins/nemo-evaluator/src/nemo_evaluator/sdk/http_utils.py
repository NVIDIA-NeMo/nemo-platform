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


def revision_selector(revision: str | None, tag: str | None) -> str | None:
    """Encode a revision selector for a ``/revisions/{selector}`` path segment.

    The route takes one selector that may be either a digest or a tag, but the SDK splits it into
    two named arguments. One argument would mean writing ``revision="blessed"`` to read a tag, which
    reads as a contradiction at the call site even though the server resolves it happily; two names
    make the caller's intent explicit and cost nothing, since both still resolve server-side.

    Returns ``None`` when neither is given — the caller then reads current content instead.
    """
    if revision is not None and tag is not None:
        raise ValueError("pass either 'revision' (a content digest) or 'tag', not both")
    selector = revision if revision is not None else tag
    return None if selector is None else quote(selector, safe="")


def platform_default_headers(platform: PlatformClient) -> dict[str, str]:
    """Return string-valued default platform headers for direct evaluator HTTP calls."""
    return {str(key): value for key, value in platform.default_headers.items() if isinstance(value, str)}


def create_job_payload(spec: EvaluateInputSpec) -> dict[str, dict[str, Any]]:
    """Serialize an evaluator job creation request body."""
    return {"spec": spec.model_dump(mode="json")}


def job_route_base_url(*, raw_base_url: str, workspace: str, job_name: str) -> str:
    """Build the stable evaluator plugin URL prefix for one submitted job."""
    encoded_workspace = quote(workspace, safe="")
    encoded_job_name = quote(job_name, safe="")
    return _join_url(raw_base_url, f"{_API_PREFIX}/v2/workspaces/{encoded_workspace}/evaluate/jobs/{encoded_job_name}")


def job_route_resource_url(*, job_base_url: str, resource_path: str) -> str:
    """Build a full evaluator plugin URL below a stable job route."""
    return _join_url(job_base_url, resource_path)


def job_route_url(*, base_url: str, workspace: str, job_name: str, suffix: str) -> str:
    """Build a full evaluator plugin job URL for a specific job-scoped operation."""
    return job_route_resource_url(
        job_base_url=job_route_base_url(raw_base_url=base_url, workspace=workspace, job_name=job_name),
        resource_path=suffix,
    )


def _join_url(root: str, relative_path: str) -> str:
    """Join a root URL and a relative path using URL parsing rules."""
    return urljoin(f"{base_url(root)}/", relative_path.lstrip("/"))
