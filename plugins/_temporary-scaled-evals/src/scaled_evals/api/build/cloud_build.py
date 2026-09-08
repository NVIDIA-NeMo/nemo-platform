# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Task sandbox image build through Google Cloud Build.

This backend is for generic GKE deployments that already store task packs in
GCS and run task images from GAR. It preserves the same user-facing upload flow:
the user uploads one task pack to scaled-evals, and Cloud Build consumes that
GCS object directly as its source archive.
"""

from __future__ import annotations

import re
import time
from typing import Any
from urllib.parse import quote

import httpx

from scaled_evals.api.build.buildkit import BuildError
from scaled_evals.api.settings import settings

_TOKEN_CACHE: tuple[str, float] | None = None

# Cloud Build issues UUID build ids. Ids reaching this module can come from a request
# path, so anything else is refused before it is interpolated into an API URL.
_BUILD_ID_RE = re.compile(
    r"\A[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\Z"
)


def build_revision_image(task_id: str, revision: int, tarball_object_key: str) -> tuple[str, str]:
    """Build a task image from the uploaded GCS archive and push it to GAR."""

    image_ref = f"{settings.image_registry}/{task_id}:rev{revision}"
    return build_image_from_gcs(tarball_object_key, image_ref)


def build_image_from_gcs(object_key: str, image_ref: str) -> tuple[str, str]:
    """Build ``image_ref`` from an uploaded GCS archive and push it to GAR."""

    build = submit_image_build_from_gcs(object_key, image_ref, wait_for_operation=True)
    build = _wait_for_build(_project(), build)
    digest = _image_digest(build, image_ref)
    return image_ref, digest


def submit_image_build_from_gcs(
    object_key: str,
    image_ref: str,
    *,
    substitutions: dict[str, str] | None = None,
    wait_for_operation: bool = False,
) -> dict[str, Any]:
    """Submit a durable Cloud Build without waiting for it to finish."""

    if settings.object_store_backend != "gcs":
        raise BuildError("Cloud Build requires OBJECT_STORE_BACKEND=gcs")
    bucket = settings.resolved_object_store_bucket()
    if not bucket:
        raise BuildError("Cloud Build requires GCS_BUCKET")
    return _create_build(
        _project(),
        bucket,
        object_key,
        image_ref,
        substitutions=substitutions,
        wait_for_operation=wait_for_operation,
    )


def get_build(build_id: str) -> dict[str, Any]:
    """Read one Cloud Build job from the configured project and location."""

    with httpx.Client(timeout=settings.gcs_request_timeout_seconds) as client:
        response = client.get(_build_url(_project(), build_id), headers=_headers())
    _raise_cloud_build("GetBuild", response)
    return response.json()


def image_digest(build: dict[str, Any], image_ref: str) -> str:
    """Return the published digest from a successful Cloud Build."""

    return _image_digest(build, image_ref)


def _create_build(
    project: str,
    bucket: str,
    object_key: str,
    image_ref: str,
    *,
    substitutions: dict[str, str] | None = None,
    wait_for_operation: bool = True,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "source": {"storageSource": {"bucket": bucket, "object": object_key}},
        "steps": [
            {
                "name": settings.cloud_build_docker_builder_image,
                "args": _docker_build_args(image_ref),
            },
            {
                "name": settings.cloud_build_docker_builder_image,
                "args": ["push", image_ref],
            },
        ],
        "images": [image_ref],
        "timeout": f"{int(settings.cloud_build_timeout_seconds)}s",
        "options": {"logging": "CLOUD_LOGGING_ONLY"},
    }
    if substitutions:
        body["substitutions"] = substitutions
        body["options"]["substitutionOption"] = "ALLOW_LOOSE"
    service_account = settings.cloud_build_service_account.strip()
    if service_account:
        body["serviceAccount"] = service_account

    with httpx.Client(timeout=settings.gcs_request_timeout_seconds) as client:
        response = client.post(_builds_url(project), headers=_headers(), json=body)
    _raise_cloud_build("CreateBuild", response)
    payload = response.json()
    if "id" in payload and "status" in payload:
        return payload
    if not wait_for_operation:
        build = _build_from_operation(payload)
        if build is None:
            raise BuildError("Cloud Build create operation did not include a build id")
        return build
    return _operation_to_build(project, payload)


def _docker_build_args(image_ref: str) -> list[str]:
    args = ["build", "-t", image_ref]
    if settings.image_build_platform:
        args.extend(["--platform", settings.image_build_platform])
    args.append(".")
    return args


def _wait_for_build(project: str, build: dict[str, Any]) -> dict[str, Any]:
    status = str(build.get("status") or "")
    deadline = time.monotonic() + settings.cloud_build_timeout_seconds
    while status not in {"SUCCESS", "FAILURE", "INTERNAL_ERROR", "TIMEOUT", "CANCELLED", "EXPIRED"}:
        if time.monotonic() >= deadline:
            raise BuildError(f"Cloud Build timed out waiting for build {build.get('id')}")
        time.sleep(settings.cloud_build_poll_interval_seconds)
        build_id = str(build.get("id") or "").strip()
        if not build_id:
            raise BuildError(f"Cloud Build response did not include build id: {build}")
        with httpx.Client(timeout=settings.gcs_request_timeout_seconds) as client:
            response = client.get(_build_url(project, build_id), headers=_headers())
        _raise_cloud_build("GetBuild", response)
        build = response.json()
        status = str(build.get("status") or "")
    if status != "SUCCESS":
        detail = build.get("failureInfo") or build.get("statusDetail") or build
        raise BuildError(f"Cloud Build task image build failed with status {status}: {detail}")
    return build


def _operation_to_build(project: str, operation: dict[str, Any]) -> dict[str, Any]:
    if operation.get("error"):
        raise BuildError(f"Cloud Build create operation failed: {operation['error']}")
    build = _build_from_operation(operation)
    if build is not None:
        return build
    operation_name = str(operation.get("name") or "").strip()
    if not operation_name:
        raise BuildError(
            f"Cloud Build create response did not include a build or operation: {operation}"
        )

    deadline = time.monotonic() + settings.cloud_build_timeout_seconds
    while not operation.get("done"):
        if time.monotonic() >= deadline:
            raise BuildError(f"Cloud Build timed out waiting for operation {operation_name}")
        time.sleep(settings.cloud_build_poll_interval_seconds)
        with httpx.Client(timeout=settings.gcs_request_timeout_seconds) as client:
            response = client.get(_operation_url(operation_name), headers=_headers())
        _raise_cloud_build("GetOperation", response)
        operation = response.json()
        if operation.get("error"):
            raise BuildError(f"Cloud Build operation failed: {operation['error']}")
        build = _build_from_operation(operation)
        if build is not None:
            return build

    raise BuildError(f"Cloud Build operation completed without a build response: {operation}")


def _build_from_operation(operation: dict[str, Any]) -> dict[str, Any] | None:
    response = operation.get("response")
    if isinstance(response, dict) and response.get("id"):
        return response
    metadata = operation.get("metadata")
    if isinstance(metadata, dict):
        build = metadata.get("build")
        if isinstance(build, dict) and build.get("id"):
            return build
    return None


def _image_digest(build: dict[str, Any], image_ref: str) -> str:
    results = build.get("results") if isinstance(build.get("results"), dict) else {}
    images = results.get("images") if isinstance(results, dict) else []
    if isinstance(images, list):
        for image in images:
            if not isinstance(image, dict):
                continue
            if str(image.get("name") or "") == image_ref and image.get("digest"):
                return str(image["digest"])
    raise BuildError(f"Cloud Build result did not include digest for {image_ref}: {build}")


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_access_token()}", "Content-Type": "application/json"}


def _project() -> str:
    project = settings.cloud_build_project.strip()
    if not project:
        raise BuildError("Cloud Build requires CLOUD_BUILD_PROJECT")
    return project


def _access_token() -> str:
    global _TOKEN_CACHE  # noqa: PLW0603
    if settings.gcs_access_token:
        return settings.gcs_access_token

    now = time.time()
    if _TOKEN_CACHE is not None:
        token, expires_at = _TOKEN_CACHE
        if expires_at - now > 60:
            return token

    with httpx.Client(timeout=settings.gcs_request_timeout_seconds) as client:
        response = client.get(settings.gcs_token_url, headers={"Metadata-Flavor": "Google"})
    _raise_cloud_build("GetAccessToken", response)
    payload = response.json()
    token = str(payload["access_token"])
    expires_in = int(payload.get("expires_in") or 300)
    _TOKEN_CACHE = (token, now + expires_in)
    return token


def _builds_url(project: str) -> str:
    location = settings.cloud_build_location.strip()
    if not location or location == "global":
        return f"{_api_base()}/v1/projects/{quote(project, safe='')}/builds"
    return (
        f"{_api_base()}/v1/projects/{quote(project, safe='')}/locations/"
        f"{quote(location, safe='')}/builds"
    )


def _build_url(project: str, build_id: str) -> str:
    if not _BUILD_ID_RE.match(build_id):
        raise BuildError("Cloud Build build id must be a UUID")
    location = settings.cloud_build_location.strip()
    if not location or location == "global":
        return (
            f"{_api_base()}/v1/projects/{quote(project, safe='')}/builds/{quote(build_id, safe='')}"
        )
    return (
        f"{_api_base()}/v1/projects/{quote(project, safe='')}/locations/"
        f"{quote(location, safe='')}/builds/{quote(build_id, safe='')}"
    )


def _operation_url(operation_name: str) -> str:
    return f"{_api_base()}/v1/{operation_name.lstrip('/')}"


def _api_base() -> str:
    return settings.cloud_build_api_base_url.rstrip("/")


def _raise_cloud_build(operation: str, response: httpx.Response) -> None:
    if response.status_code < 400:
        return
    try:
        payload = response.json()
    except ValueError:
        payload = response.text
    raise BuildError(f"{operation} returned HTTP {response.status_code}: {payload}")
