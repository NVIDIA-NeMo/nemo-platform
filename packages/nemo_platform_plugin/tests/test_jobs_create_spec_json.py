# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Regression: plugin create_job forwards transformed specs in JSON mode."""

from __future__ import annotations

import base64
import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from nemo_platform_plugin.dependencies import get_entity_client, get_sdk_client
from nemo_platform_plugin.jobs.api_factory import (
    ContainerSpec,
    CPUExecutionProviderSpec,
    PlatformJobSpec,
    PlatformJobStep,
    job_route_factory,
)
from pydantic import BaseModel, ConfigDict
from starlette.testclient import TestClient

# Non-UTF-8 bytes like a cloudpickle metric bundle blob.
_PICKLE_BYTES = b"\x80\x04\x95\x00\x00\x00"


class _InputSpec(BaseModel):
    label: str = "metric"


class _OutputSpec(BaseModel):
    model_config = ConfigDict(ser_json_bytes="base64", val_json_bytes="base64")

    blob: bytes


def _to_output(
    input_spec: _InputSpec,
    workspace: str,
    entity_client: object,
    job_name: str | None,
    sdk: object,
) -> _OutputSpec:
    del input_spec, workspace, entity_client, job_name, sdk
    return _OutputSpec(blob=_PICKLE_BYTES)


def _compiler(
    workspace: str,
    original_spec: _InputSpec,
    transformed_spec: _OutputSpec,
    entity_client: object,
    job_name: str | None,
    sdk: object,
) -> PlatformJobSpec:
    del workspace, original_spec, transformed_spec, entity_client, job_name, sdk
    return PlatformJobSpec(
        steps=[
            PlatformJobStep(
                name="step",
                executor=CPUExecutionProviderSpec(
                    provider="cpu",
                    profile="default",
                    container=ContainerSpec(image="test"),
                ),
                config={},
            )
        ]
    )


def _mock_create_response(spec: dict[str, object]) -> MagicMock:
    job = SimpleNamespace(
        id="job-1",
        name="test-job",
        description=None,
        workspace="default",
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
        spec=spec,
        status="created",
        status_details=None,
        error_details=None,
        ownership=None,
        custom_fields=None,
    )
    response = MagicMock()
    response.data.return_value = job
    return response


def test_create_job_forwards_transformed_spec_in_json_mode() -> None:
    """Binary fields in transformed specs must be base64 strings, not raw bytes."""
    router = job_route_factory(
        service_name="widgets",
        job_type="Widget",
        job_input=_InputSpec,
        job_output=_OutputSpec,
        input_to_output=_to_output,
        platform_job_config_compiler=_compiler,
    )
    app = FastAPI()
    app.include_router(router, prefix="/apis/widgets/v2/workspaces/{workspace}")
    app.dependency_overrides[get_sdk_client] = lambda: MagicMock()
    app.dependency_overrides[get_entity_client] = lambda: MagicMock()

    captured_body: dict[str, object] = {}

    async def _create_job(*, workspace: str, body: object) -> MagicMock:
        del workspace
        captured_body["body"] = body
        expected_spec = {"blob": base64.b64encode(_PICKLE_BYTES).decode("ascii")}
        return _mock_create_response(expected_spec)

    mock_jobs = SimpleNamespace(create_job=_create_job)

    client = TestClient(app)
    with patch(
        "nemo_platform_plugin.jobs.api_factory.client_from_platform",
        return_value=mock_jobs,
    ):
        response = client.post("/apis/widgets/v2/workspaces/default/jobs", json={"spec": {"label": "metric"}})

    assert response.status_code == 201, response.text
    body = captured_body["body"]
    assert body is not None
    spec = body.spec if hasattr(body, "spec") else body["spec"]  # type: ignore[index]
    blob = spec["blob"] if isinstance(spec, dict) else spec.blob
    assert isinstance(blob, str), f"expected base64 string, got {type(blob)}"
    assert blob == base64.b64encode(_PICKLE_BYTES).decode("ascii")
    # Must be JSON-serializable for the typed jobs client (raw bytes would 500).
    json.dumps({"spec": spec})
