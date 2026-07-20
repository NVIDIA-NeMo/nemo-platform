# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""PreparedRequest contract tests for VirtualModel CRUD endpoints."""

from __future__ import annotations

import json
from typing import get_args, get_origin

from nemo_platform_plugin.client.types import Paginated, PreparedRequest
from nemo_platform_plugin.inference_middleware import VirtualModel
from nemo_platform_plugin.virtual_models import endpoints
from nemo_platform_plugin.virtual_models.types import (
    CreateVirtualModelRequest,
    UpdateVirtualModelRequest,
    VirtualModelInferenceConfig,
)

_PATH = "/apis/inference-gateway/v2/workspaces/{workspace}/virtual-models"


def _json_body(prepared: PreparedRequest) -> dict[str, object]:
    assert isinstance(prepared.content, bytes)
    return json.loads(prepared.content)


def test_create_virtual_model_request() -> None:
    body = CreateVirtualModelRequest(
        name="router",
        default_model_entity="default/llama",
        models=[VirtualModelInferenceConfig(model="default/llama")],
    )

    prepared = endpoints.create_virtual_model(workspace="default", body=body)

    assert isinstance(prepared, PreparedRequest)
    assert prepared.method == "POST"
    assert prepared.path_template == _PATH
    assert prepared.path_params == {"workspace": "default"}
    assert prepared.content_type == "application/json"
    assert _json_body(prepared) == {
        "name": "router",
        "default_model_entity": "default/llama",
        "models": [{"model": "default/llama"}],
    }
    assert prepared.response_type is VirtualModel


def test_create_virtual_model_workspace_is_optional() -> None:
    prepared = endpoints.create_virtual_model(body=CreateVirtualModelRequest(name="router"))

    assert prepared.path_params == {}


def test_list_virtual_models_request() -> None:
    prepared = endpoints.list_virtual_models(
        workspace="default",
        query_params={
            "page": 2,
            "page_size": 10,
            "sort": "created_at",
            "filter": "name:router",
            "exclude_autoprovisioned": True,
        },
    )

    assert prepared.method == "GET"
    assert prepared.path_template == _PATH
    assert prepared.path_params == {"workspace": "default"}
    assert prepared.query_params == {
        "page": 2,
        "page_size": 10,
        "sort": "created_at",
        "filter": "name:router",
        "exclude_autoprovisioned": True,
    }
    assert get_origin(prepared.response_type) is Paginated
    assert get_args(prepared.response_type)[0] is VirtualModel


def test_get_virtual_model_request() -> None:
    prepared = endpoints.get_virtual_model(workspace="default", name="router")

    assert prepared.method == "GET"
    assert prepared.path_template == _PATH + "/{name}"
    assert prepared.path_params == {"workspace": "default", "name": "router"}
    assert prepared.content is None
    assert prepared.response_type is VirtualModel


def test_update_virtual_model_request_excludes_unset_fields() -> None:
    body = UpdateVirtualModelRequest(default_model_entity=None, request_middleware=[])

    prepared = endpoints.update_virtual_model(workspace="default", name="router", body=body)

    assert prepared.method == "PATCH"
    assert prepared.path_template == _PATH + "/{name}"
    assert prepared.path_params == {"workspace": "default", "name": "router"}
    assert _json_body(prepared) == {"default_model_entity": None, "request_middleware": []}
    assert prepared.response_type is VirtualModel


def test_delete_virtual_model_request() -> None:
    prepared = endpoints.delete_virtual_model(workspace="default", name="router")

    assert prepared.method == "DELETE"
    assert prepared.path_template == _PATH + "/{name}"
    assert prepared.path_params == {"workspace": "default", "name": "router"}
    assert prepared.content is None
    assert prepared.response_type is None
